import os
import re
import time
import json
import math
import shutil
import hashlib
import xml.dom.minidom
from typing import TYPE_CHECKING

import jinja2 as jj
import markdown
import systemrdl

from systemrdl.node import Node, RootNode, AddressableNode
from systemrdl.node import AddrmapNode, MemNode, RegfileNode, RegNode, FieldNode, SignalNode
from systemrdl.component import Addrmap, Mem, Regfile, Reg, Field, Signal
from systemrdl import rdltypes
from systemrdl.source_ref import FileSourceRef, DetailedFileSourceRef

from .stringify import stringify_rdl_value
from .__about__ import __version__

if TYPE_CHECKING:
    from typing import Any, Optional, Tuple, List, Dict, Union
    from systemrdl.source_ref import SourceRefBase

# debug
import pprint

class MarkupExporter:
    def __init__(self, **kwargs: 'Any') -> None:
        """
        Constructor for the Markup exporter class

        Parameters
        ----------
        markdown_inst: ``markdown.Markdown``
            Override the class instance of the Markdown processor.
            See the `Markdown module <https://python-markdown.github.io/reference/#Markdown>`_
            for more details.
        user_template: str
            Path to a user-defined template file.
        """
        self.output_file      = "" # type: str
        self.skip_not_present = kwargs.pop("skip_not_present", True) # type: ignore
        markdown_inst         = kwargs.pop("markdown_inst", None) # type: Optional[markdown.Markdown]
        user_template         = kwargs.pop("user_template", None)

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

        if markdown_inst is None:
            self.markdown_inst = markdown.Markdown(
                extensions = [
                    'extra',
                    'admonition',
                    'mdx_math',
                ],
                extension_configs={
                    'mdx_math':{
                        'add_preview': True
                    }
                }
            )
        else:
            self.markdown_inst = markdown_inst

        if user_template:
            loader = jj.ChoiceLoader([
                jj.FileSystemLoader(user_template),
                jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
            ]) # type: jj.BaseLoader
        else:
            loader = jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))

        self.jj_env = jj.Environment(
            loader=loader,
            autoescape=jj.select_autoescape(['html']),
            undefined=jj.StrictUndefined,
            extensions=['jinja2_slug.SlugExtension', 'jinja2.ext.do', 'jinja2.ext.debug']
        )


    def export(self, nodes: 'Union[Node, List[Node]]', output_file: str, **kwargs: 'Dict[str, Any]') -> None:
        """
        Perform the export!

        Parameters
        ----------
        nodes: systemrdl.Node
            Top-level node to export.
            Can be the top-level `RootNode` or any internal `AddrmapNode`.
            Can also be a list of `RootNode` and any internal `AddrmapNode`.
        output_file: str
            Exporter output file name.
        skip_not_present: bool
            (optional) Control whether nodes with ispresent=false are generated.
            Default is True
        """

        # if not a list, create a list with a single element
        if not isinstance(nodes, list):
            nodes = [nodes]

        # if it is the root node, skip to top addrmap
        for i, node in enumerate(nodes):
            if isinstance(node, RootNode):
                nodes[i] = node.top

        # Traverse trees
        context = {}
        for node in nodes:
            if node.get_property('bridge'):
                node.env.msg.warning(
                    "Markup generator does not have proper support for bridge addmaps yet. The 'bridge' property will be ignored.",
                    node.inst.property_src_ref.get('bridge', node.inst.inst_src_ref)
                )

        #breakpoint()
#        pprint.pp(context)

#        template = self.jj_env.get_template("markup-absolute-systemrdl.md.jinja")
        template = self.jj_env.get_template("markup-relative-systemrdl.md.jinja")
        template.globals.update(type = type)
        template.globals.update(print = print)
        template.globals.update(isinstance = isinstance)
        template.globals.update(systemrdl = systemrdl)
        # TODO: this is not a simple jinja context, just the top node
        components = {node.inst.type_name : self.visit_component([node]) for node in nodes}
        stream = template.stream({'nodes': nodes, 'components': components})
#        stream = template.stream(context)
        stream.dump(output_file)


    def visit_component(self, nodes: 'List(Node)') -> dict:
        context = {}
        context['instances'] = nodes

        # organize nodes into an ordered dictionary of definitions
        # each containing a list of instances
        components = {}
        for child in nodes[0].children():
            type_name = child.inst.type_name
            if type_name in components.keys():
                components[type_name].append(child)
            else:
                components[type_name] = [child]
        for type_name in components.keys():
            components[type_name] = self.visit_component(components[type_name])
        context['components'] = components

        return context


    def get_child_addr_digits(self, node: AddressableNode) -> int:
        return math.ceil(math.log2(node.size) / 4)


    def get_node_html_desc(self, node: Node, increment_heading: int=0) -> 'Optional[str]':
        """
        Wrapper function to get HTML description
        If no description, returns None

        Performs the following transformations on top of the built-in HTML desc
        output:
        - Increment any heading tags
        - Transform img paths that point to local files. Copy referenced image to output
        """

        desc = node.get_html_desc(self.markdown_inst)
        if desc is None:
            return desc

        return desc

    def try_resolve_rel_path(self, src_ref: 'Optional[SourceRefBase]', relpath: str) -> 'Optional[str]':
        """
        Test if the source reference's base path + the relpath points to a file
        If it works, returns the new path.
        If not, return None
        """

        if not isinstance(src_ref, FileSourceRef):
            return None

        path = os.path.join(os.path.dirname(src_ref.path), relpath)
        if not os.path.exists(path):
            return None

        return path


def friendly_access(obj: 'Any') -> str:
    """
    Convert access types into a human-friendly string
    """
    lut = {
        rdltypes.AccessType.na      : "Not Accessible",
        rdltypes.AccessType.rw      : "Readable and Writable",
        rdltypes.AccessType.r       : "Read-only",
        rdltypes.AccessType.w       : "Write-only",
        rdltypes.AccessType.rw1     : "Readable. Writable once.",
        rdltypes.AccessType.w1      : "Writable once",
        rdltypes.OnReadType.rclr    : "Clear on read",
        rdltypes.OnReadType.rset    : "Set on read",
        rdltypes.OnWriteType.woset  : "Bitwise write 1 to set",
        rdltypes.OnWriteType.woclr  : "Bitwise write 1 to clear",
        rdltypes.OnWriteType.wot    : "Bitwise write 1 to toggle",
        rdltypes.OnWriteType.wzs    : "Bitwise write 0 to set",
        rdltypes.OnWriteType.wzc    : "Bitwise write 0 to clear",
        rdltypes.OnWriteType.wzt    : "Bitwise write 0 to toggle",
        rdltypes.OnWriteType.wclr   : "Clear on write",
        rdltypes.OnWriteType.wset   : "Set on write",
    }
    return lut.get(obj, "")
