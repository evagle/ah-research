# CAICT

Use CAICT for ICT-related claims: telecommunications, cloud services, AI,
digital economy, industrial internet, data infrastructure, and cybersecurity.
Do not route it as a general consumer-industry researcher.

## Direct Search

1. Search the official host for the industry, metric, year, and document type:
   `site:caict.ac.cn/kxyj/qwfb ("市场份额" OR "市场规模") "{industry}" filetype:pdf`.
2. Search both `kxyj/qwfb/bps` (white papers) and `kxyj/qwfb/ztbg`
   (special reports). Repeat in English against
   `caict.ac.cn/english/research/whitepapers`.
3. Open the resulting `caict.ac.cn` PDF directly. The HTML library may return
   412 while the official PDF remains publicly retrievable; the library error
   does not make the PDF unavailable.
4. Capture report number, title, issuing institute, publication date, page or
   figure, period, geography, units, denominator, source note, and methodology.

Cloud white papers are a recurring series and may contain market size,
growth, vendor rankings, and market-share figures. Search each required year
independently because the file identifier changes by edition.

If a figure is image-based, extract or OCR it locally and verify the totals
against the surrounding text and footnotes. Store only extracted values,
official URL, scope, and evidence metadata in Git; do not commit the PDF or
figure image as a research artifact.

## Evidence

A directly retrieved CAICT report is high-authority evidence for the
measurements CAICT produced. A prospectus or listing application that clearly
attributes a table to CAICT remains usable evidence even when the standalone
CAICT report cannot be recovered. Grade the claim from document authenticity,
attribution, scope, methodology disclosure, and commissioning context, not
from URL reachability alone.
