"""The TeX of provenance (V2, V34): written to move into texmodel (N5, V9), so it imports nothing of texpkg.

A package declares `\\<prefix>ProvenanceInfo`, which says what it is and, once a provenance file has been written beside
the document, which stamp and time it was materialised with. The file renews two macros and adds the same text to the
PDF's Info dictionary when PDF management is active.
"""

import re
import textwrap

STAMP = re.compile(r"[A-Za-z0-9.+:/@ -]*")  # text that is the same in TeX, in a PDF string and on the page
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def file_name(package: str) -> str:
    return f"{package}-provenance.sty"


def info(package: str, version: str, stamp: str, time: str) -> str:
    """The text `\\<prefix>ProvenanceInfo` prints, parts that are empty left out."""
    return f"{package} {version}" + (f", stamp {stamp}" if stamp else "") + (f", materialised {time}" if time else "")


def declarations(prefix: str, package: str, version: str) -> str:
    """The block a package's `.sty` carries: both parts empty, the command that composes them, the file read if there.
    Declared with `\\def`, not `\\newcommand`, which makes a `\\long` macro: `\\ifx` against `\\@empty` never holds."""
    return textwrap.dedent(
        rf"""
        \makeatletter
        \def\{prefix}ProvenanceStamp{{}}
        \def\{prefix}ProvenanceTime{{}}
        \newcommand{{\{prefix}ProvenanceInfo}}{{%
          {package} {version}%
          \ifx\{prefix}ProvenanceStamp\@empty\else, stamp \{prefix}ProvenanceStamp\fi
          \ifx\{prefix}ProvenanceTime\@empty\else, materialised \{prefix}ProvenanceTime\fi}}
        \InputIfFileExists{{{file_name(package)}}}{{}}{{}}
        \makeatother
        """
    ).strip()


def companion(prefix: str, package: str, version: str, stamp: str, time: str) -> str:
    """The provenance file: it renews the stamp and the time, and adds the text to the PDF's Info dictionary as
    `/<Prefix>Provenance` when PDF management is active (without it the entry is skipped)."""
    text = info(package, version, stamp, time)
    key = prefix.capitalize() + "Provenance"
    return textwrap.dedent(
        rf"""
        % {package}: what this directory was materialised from. Generated; do not edit.
        \def\{prefix}ProvenanceStamp{{{stamp}}}
        \def\{prefix}ProvenanceTime{{{time}}}
        \ifdefined\IfPDFManagementActiveTF
          \IfPDFManagementActiveTF
            {{\csname pdfmanagement_add:nnn\endcsname{{Info}}{{{key}}}{{(\detokenize{{{text}}})}}}}
            {{}}
        \fi
        """
    ).lstrip("\n")


def read(text: str, prefix: str) -> tuple[str, str]:
    """The stamp and the time a provenance file holds, or two empty strings if it holds none."""
    stamp = re.search(rf"^\\def\\{prefix}ProvenanceStamp\{{(.*)\}}$", text, re.MULTILINE)
    time = re.search(rf"^\\def\\{prefix}ProvenanceTime\{{(.*)\}}$", text, re.MULTILINE)
    return (stamp[1] if stamp else "", time[1] if time else "")
