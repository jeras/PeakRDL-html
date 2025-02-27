from typing import TYPE_CHECKING

from peakrdl.plugins.exporter import ExporterSubcommandPlugin #pylint: disable=import-error
from peakrdl.config import schema #pylint: disable=import-error

from .exporter import JinjaExporter

if TYPE_CHECKING:
    import argparse
    from systemrdl.node import AddrmapNode


class Exporter(ExporterSubcommandPlugin):
    short_desc = "Generate jinja documentation"
    long_desc = "Generate jinja (Markdown, AsciiDoc, reStructuredText) documentation pages."

    cfg_schema = {
        "user_template": schema.DirectoryPath(),
    }

    def do_export(self, top_node: 'AddrmapNode', options: 'argparse.Namespace') -> None:

        jinja = JinjaExporter(
            user_template=self.cfg['user_template'],
        )
        jinja.export(
            top_node,
            options.output,
        )
