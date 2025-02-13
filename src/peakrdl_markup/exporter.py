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
        user_context: dict
            Additional context variables to load into the template namespace.
        show_signals: bool
            Show signal components. Default is False
        extra_doc_properties: List[str]
            List of properties to explicitly document.
            Nodes that have a property explicitly set will show its value in a
            table in the node's description.
            Use this to bring forward user-defined properties, or other built-in
            properties in your documentation.
        """
        self.output_dir = "" # type: str
        self.skip_not_present = kwargs.pop("skip_not_present", True) # type: ignore
        self.show_signals     = kwargs.pop("show_signals", False)
        self.user_context     = kwargs.pop("user_context", {})
        self.extra_properties = kwargs.pop("extra_doc_properties", []) # type: List[str]
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
            undefined=jj.StrictUndefined
        )


    def export(self, nodes: 'Union[Node, List[Node]]', output_dir: str, **kwargs: 'Dict[str, Any]') -> None:
        """
        Perform the export!

        Parameters
        ----------
        nodes: systemrdl.Node
            Top-level node to export.
            Can be the top-level `RootNode` or any internal `AddrmapNode`.
            Can also be a list of `RootNode` and any internal `AddrmapNode`.
        output_dir: str
            Exporter output directory.
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
            self.current_top_node = node
            if node.get_property('bridge'):
                node.env.msg.warning(
                    "Markup generator does not have proper support for bridge addmaps yet. The 'bridge' property will be ignored.",
                    node.inst.property_src_ref.get('bridge', node.inst.inst_src_ref)
                )
            context['nodes'] = self.visit_node(node)
            context['components'] = {node.type_name: self.visit_component(node)}


        #breakpoint()
        pprint.pp(context)

        # Make sure output directory structure exists
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        template = self.jj_env.get_template("markup-relative.md.jinja")
        stream = template.stream(context)
        output_path = os.path.join(self.output_dir, "test.md")
        stream.dump(output_path)


    def visit_node(self, node: Node) -> dict:

        context = {
            'class'    : node.inst.__class__.__name__,
            'type_name': node.type_name,
            'instance' : node.inst.inst_name,
            'offset'   : node.inst.addr_offset,
            'address'  : node.absolute_address,
            'size'     : node.size,
            'name'     : node.get_property('name'),
            'desc'     : node.get_property('desc'),
        }
        if node.inst.is_array:
            context['dims'] = node.inst.array_dimensions
            context['stride'] = node.inst.array_stride
            context['indexes'] = [0] * len(node.inst.array_dimensions)

        if   isinstance(node, AddrmapNode):
            context['type'] = "addrmap"
        elif isinstance(node, RegfileNode):
            context['type'] = "regfile"
        elif isinstance(node, RegNode):
            context['type'] = "reg"
            context_fields = list()
            for i, field in enumerate(node.fields(skip_not_present=self.skip_not_present)):

                field_reset = field.get_property("reset", default=0)
                if isinstance(field_reset, Node):
                    # Reset value is a reference. Dynamic RAL data does not
                    # support this, so stuff a 0 in its place
                    field_reset = 0

                context_field = {
                    'type_name': field.type_name,
                    'lsb'      : field.inst.lsb,
                    'msb'      : field.inst.msb,
                    'reset'    : field_reset,
                    'sw'       : field.get_property('sw').name,
                    'hw'       : field.get_property('hw').name,
#                    'onread'   : field.get_property('onread').name,
#                    'onwrite'  : field.get_property('onwrite').name,
                    'name'     : field.get_property('name'),
                    'desc'     : field.get_property('desc'),
                }

                field_enum = field.get_property("encode")
                if field_enum is not None:
                    context_field['encode'] = True
                    context_field['disp'] = 'E'

                context_fields.append(context_field)

            context['fields'] = context_fields

        # Recurse to children
        children = list()
        for child in node.children(skip_not_present=self.skip_not_present):
            if not isinstance(child, AddressableNode):
                continue
            children.append(self.visit_node(child))

        # Generate page for this node
        context['nodes'] = children

        return context

    def visit_component(self, node: Node) -> dict:

        context = {}

        context['class']     = node.inst.__class__.__name__
        context['type_name'] = node.inst.type_name
        context['instance']  = node.inst.inst_name
        context['name']      = node.get_property('name')
        context['desc']      = node.get_property('desc')

        if isinstance(node.inst, (Addrmap, Regfile, Reg)):
            context['offset']  = node.inst.addr_offset
            if node.inst.is_array:
                context['dims']    = node.inst.array_dimensions
                context['stride']  = node.inst.array_stride
                context['indexes'] = [0] * len(node.inst.array_dimensions)
        elif isinstance(node.inst, Field):
            field_reset = node.get_property("reset", default=0)
            if isinstance(field_reset, Node):
                # Reset value is a reference. Dynamic RAL data does not
                # support this, so stuff a 0 in its place
                field_reset = 0

            context['lsb']       = node.inst.lsb
            context['msb']       = node.inst.msb
            context['reset']     = field_reset
            context['sw']        = node.get_property('sw').name
            context['hw']        = node.get_property('hw').name
##          context['onread']    = node.get_property('onread').name
##          context['onwrite']   = node.get_property('onwrite').name

            field_enum = node.get_property("encode")
            if field_enum is not None:
                context_field['encode'] = True
                context_field['disp'] = 'E'

        # Recurse to children
        children = list()
        for child in node.children(skip_not_present=self.skip_not_present):
            if not isinstance(child, AddressableNode):
                continue
            children.append(self.visit_node(child))

        # Generate page for this node
        context['nodes'] = children

        # organize nodes into an ordered dictionary of definitions
        # each containing a list of instances
        components = {}
        for child in node.children(skip_not_present=self.skip_not_present):
            print("==============================")
            print(child)
            type_name = child.inst.type_name
            if type_name in components.keys():
                components[type_name]['instances'].append(child)
            else:
                components[type_name] = self.visit_component(child)
                components[type_name]['instances'] = [child]

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

    def get_enum_html_desc(self, enum_member) -> str: # type: ignore
        s = enum_member.get_html_desc(self.markdown_inst)
        if s:
            return s
        else:
            return ""


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


    def has_extra_property_doc(self, node: Node) -> bool:
        """
        Returns True if node has a property set that is to be explicitly
        documented.
        """
        for prop in self.extra_properties:
            if prop in node.list_properties():
                return True
        return False


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


def has_enum_encoding(field: FieldNode) -> bool:
    """
    Test if field is encoded with an enum
    """
    return "encode" in field.list_properties()


def reg_fields_are_low_to_high(node: RegNode) -> bool:
    for field in node.fields():
        if field.msb < field.lsb:
            return True
    return False
