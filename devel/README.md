```
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install systemrdl-compiler
python3 -m pip install peakrdl
python3 -m pip install jinja2
python3 -m pip install jinja2-slug
python3 -m pip install markupsafe==2.0.1

# development install of project
python3 -m pip install -e ../

# run test
peakrdl jinja example32.rdl -o example32.md
```

# Ideas

I am planning to work on this problem, and a few other features:

- array unrolling to be made optional,
- linking between table element and its description section,
- support for Markdown, AsciiDoc, reStructuredText, by choosing a Jinja template,

## Multiple instances and array instances

### Inspiration

I tried to find some data sheets containing a register map to be used as inspiration. First I checked the CSR definition for RISC-V, but those are very specific, even containing features not present in the SystemRDL standard. The other two are my first tries and they look good. I was also thinking to look into some NPX ARM Microcontrollers.

1. [Zynq UltraScale+ Devices Register Reference](https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/Overview)
2. [RP2350 Datasheet](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf) chapter _2.2. Address Map_

#### Xilinx

In the Xilinx document I noticed the following:

1. The following hierarchy is used:

   - _x_ Top `addrmap` containing a table of `regfile` instances with links to sections _x.y_ for each `regfile` component definition/description.
   - _x.y_ For each `regfile` a table of `reg` instances with links to sections _x.y.z_ for each `reg` component definition/description.
   - _x.y.z_ For each `reg` a table of `field` instances, without links, the description is part of the table.

   This hierarchy avoids mixing different component types on the same hierarchical level,
   For example a `addrmap` or `regfile` containing a mix of both `regfile` and `reg` instances.
   This approach reduces the number of complex interactions within a documentation generator.

2. Arrays of `regfile` and `reg` instances are **unrolled** inside tables.
   There might be cases, where an array range is used [0:N-1], but I did not see any yet.
   The arrays were of length around 4, some of length 16.

3. There are two types of unrolling:

   1. In case the `regfile` and `reg` instances share the same definition/description section
      like [ZDMA module](https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/ZDMA-Module)
      are appended the `n` suffix (no separator, index) in tables.

      In this case, there is also a list of _base address_ for all `regfile` instances,
      and a list of _absolute address_ for the same `reg` in all `regfile` instances.

      https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/ZDMA_ERR_CTRL-ZDMA-Register

   2. Some `regfile` arrays use the `_n` suffix (`_` separator and index) and also link to separate definitions.
      For example `CORESIGHT_A53_CTI_0`/`1`/`2`/`3`.

      It seems the use of the suffix is not strict, since some registers have
      the suffix without the separator and separate definitions.

      https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/CTIINEN0-A53_CTI_0-Register

   I did not check yet, whether the repeated definitions for apparently identical `regfile`/`reg` instances
   also have identical descriptions, but it appears they do.
   The _base address_ for `regfile` and _absolute address_ for `reg` are distinct as expected.

   There are also cases with indexes which are not arrays.
   Like control registers which do not fit into 32-bits and are therefore split into CTRL0, CTRL1.

   https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/ZDMA_CH_CTRL0-ZDMA-Register

#### Raspberry PI

An example of multiple instances of the same `regfile` would be the 3 PIO instances
within the AHB `, see section _2.2.5. AHB Registers_.
All three instances link to the same PIO documentation.

At the end of the PIO documentation there is section _11.7. List of Registers_.
At the beginning of the section are again listed the base addresses for each PIO instance.
Curiously this part of the document was not updated to list 3 PIO compared to the old chip with just 2 PIO.

The documentation for individual registers does not list the absolute address for each PIO instance,
instead just a an offset is provided.

### Proposed solutions

1. By default do not duplicate component description sections for multiple instances or arrays.
   This should be straight forward as long as the the instances are within the same parent.
   To avoid special accommodations for parameters, each parameterization shall have a separate section.
2. By default unroll all arrays up to a threshold (could be 4 or 8 by default provided from CLI).
3. Within the description for a duplicated component optionally provide base/absolute addresses
   for each instance array element. For arrays only up to the array unrolling threshold.
4. Provide user defined properties for duplication, unrolling, that can be applied to each instance separately.

## Linking between table element and its description section

For example a link from the identifier of a register in a table
to the section fully documenting this register (similar for fields, ...).

Initially I thought this would be difficult, since Markdown links to headers
are constructed from the header text, and this would not work well if there are
multiple headers with the same text.
Than I noticed at least GitHub is appending an additional index (`-n`)
to the `n`-th heading with the same text.
So it would be extra work to track this index, but it is doable.

AsciiDoc provides the [ID Attribute](https://docs.asciidoctor.org/asciidoc/latest/attributes/id/)
which provides an unique path for links.

There might be something similar for reStructuredText, I did not check yet.

## Support for multiple formatted text languages

The three document formats Markdown, AsciiDoc, reStructuredText all have a similar approach.
They are based on human readable text, and are often parsed/rendered
by version control web interfaces (GitHub, GitLab, ...).

Since all three have similar features, it would probably be possible to support
all three formats by the same Python jude, just by switching the Jinja template.

It wold probably make sense to find a new name for such a combined tool?

- PeakRDL-TextDoc,
- PeakRDL-DocText,
- PeakRDL-DocGen.

## Implementation plan

1. example SystemRDL file showcasing desired features
2. 
4. add more Jinja2 templates
5. update documentation 