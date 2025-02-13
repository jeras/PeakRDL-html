from typing import TYPE_CHECKING

from peakrdl.plugins.exporter import ExporterSubcommandPlugin #pylint: disable=import-error
from peakrdl.config import schema #pylint: disable=import-error

from .exporter import MarkupExporter

if TYPE_CHECKING:
    import argparse
    from systemrdl.node import AddrmapNode


class Exporter(ExporterSubcommandPlugin):
    short_desc = "Generate Markup documentation"
    long_desc = "Generate Markup (Markdown, AsciiDoc, reStructuredText) documentation pages."

    cfg_schema = {
        "user_template": schema.DirectoryPath(),
        "extra_doc_properties": [schema.String()],
    }


    def add_exporter_arguments(self, arg_group: 'argparse.ArgumentParser') -> None:
        arg_group.add_argument(
            "--show-signals",
            dest="show_signals",
            default=False,
            action="store_true",
            help="Show signal components in generated doc pages"
        )


    def do_export(self, top_node: 'AddrmapNode', options: 'argparse.Namespace') -> None:

        markup = MarkupExporter(
            show_signals=options.show_signals,
            user_template=self.cfg['user_template'],
            extra_doc_properties=self.cfg['extra_doc_properties'],
        )
        markup.export(
            top_node,
            options.output,
        )
