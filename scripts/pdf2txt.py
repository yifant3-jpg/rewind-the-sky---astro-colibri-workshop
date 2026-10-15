"""Extract text from a downloaded PDF. Usage: python -I scripts/pdf2txt.py <dir>   (reads <dir>/paper.pdf, writes <dir>/paper.txt)"""
import sys
from pathlib import Path
from pypdf import PdfReader
d = Path(sys.argv[1])
r = PdfReader(d / "paper.pdf")
txt = "\n".join(f"\n<<<PAGE {i+1}>>>\n" + (p.extract_text() or "") for i, p in enumerate(r.pages))
(d / "paper.txt").write_text(txt)
print(d, len(r.pages), "pages,", len(txt), "chars")
