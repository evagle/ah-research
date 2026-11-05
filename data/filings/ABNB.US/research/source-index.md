# ABNB.US latest-report source index

Observation date: 2026-09-18

## Primary issuer and filing evidence

| ID | Source | Identity and period | Local artifact | SHA-256 | Use |
|---|---|---|---|---|---|
| S1 | [Airbnb Q2 2026 Form 10-Q mirror](https://d18rn0p25nwr6d.cloudfront.net/CIK-0001559720/1cc15dc3-ddb9-420b-8e3d-162830b620a3.pdf) | CIK 0001559720; accession 0001559720-26-000027; filed 2026-08-06; period 2026-06-30; unaudited | `data/filings/ABNB.US/ABNB-2026-Q2-10Q.pdf` | `fde41d6d715e0f3ab09a86d751f31b053ae81433cd715512c8e174461520e941` | GAAP statements, expense detail, cash flow, balance sheet, risk updates |
| S2 | [Airbnb 2025 Form 10-K HTML mirror](https://d18rn0p25nwr6d.cloudfront.net/CIK-0001559720/b1377c3d-6876-441c-aac3-6c5e786d0798.html) and [PDF mirror](https://d18rn0p25nwr6d.cloudfront.net/CIK-0001559720/52fc9020-faa3-4ed3-b6e3-9a982ecdda93.pdf) | CIK 0001559720; accession 0001559720-26-000004; filed 2026-02-12; period 2025-12-31; audited | `data/filings/ABNB.US/ABNB-2025-10K.pdf` | `48a78febd054e9a1e8b58207a6f7bf38eb7a2691cfab4acf5b173941c49c3e92` | Audited baseline, accounting policy, structural risks |
| S3 | [Airbnb Q2 2026 Shareholder Letter](https://s26.q4cdn.com/656283129/files/doc_financials/2026/q2/v2/Airbnb-Q2-2026-Shareholder-Letter.pdf) | Published 2026-08-06; Q2 2026; Airbnb first-party; same earnings cycle | `data/filings/ABNB.US/Airbnb-Q2-2026-Shareholder-Letter.pdf` | `913155a2c62ffcd038aa42fee57c8ca84d7ac5e26d4fe395240a64100d880961` | Operating KPIs, strategy actions, guidance, non-GAAP reconciliations |

## Independent market evidence

| ID | Source | Checked | Accepted claim | Boundary |
|---|---|---|---|---|
| S4 | [CNBC, Airbnb stock soars 9% on earnings and revenue beat](https://www.cnbc.com/2026/08/06/airbnb-abnb-q2-earningsreport.html) | 2026-09-18 | 9% extended-trading move; LSEG consensus of $1.25 EPS and $3.58B revenue; Q3 consensus revenue of $4.61B | Market reaction and expectations only; does not prove business causality |
| S5 | [Reuters via CNA, Airbnb hits four-year high](https://www.channelnewsasia.com/business/airbnb-hits-four-year-high-investors-cheer-revenue-forecast-raise-ai-payoff-6306291) | 2026-09-18 | 14% intraday rise to a more-than-four-year high; reporting and analyst attribution to raised guidance, resilient demand, new verticals, and AI efficiency | Credible external attribution, not a controlled causal test; valuation multiple was not independently reconstructed |

## SEC reachability and selection state

- The SEC issuer mapping and catalog identity previously resolved `ABNB.US` to CIK `0001559720`. The latest qualifying report on the observation date is the Q2 2026 10-Q, accession `0001559720-26-000027`; the audited baseline is the 2025 10-K, accession `0001559720-26-000004`.
- Live SEC replay from the current runtime ended in Akamai `SEC 403` responses identifying an undeclared automated tool. Status: `dependency_failure`, not factual absence. The report therefore does not claim a successful live SEC revalidation on 2026-09-18.
- Comparable-quarter periods selected for analysis are 2026-03-31, 2025-09-30, 2025-06-30, and 2025-03-31. The current report uses the issuer's same-definition quarterly table for trend checks because the four individual filing artifacts were not acquired in this run.
- Same-cycle shareholder-letter evidence is present. The current local bundle does not include the corresponding SEC-filed 8-K HTML exhibit, so narrative facts cite the immutable issuer PDF and remain explicitly bounded.

## Citation records

`S1-Q2-OPS`: source_type=filing_pdf; official_url=https://d18rn0p25nwr6d.cloudfront.net/CIK-0001559720/1cc15dc3-ddb9-420b-8e3d-162830b620a3.pdf; artifact_path=data/filings/ABNB.US/ABNB-2026-Q2-10Q.pdf; artifact_sha256=fde41d6d715e0f3ab09a86d751f31b053ae81433cd715512c8e174461520e941; page=4; quote="Revenue $3,608 million; income from operations $758 million; net income $816 million."

`S3-Q2-KPI`: source_type=issuer_pdf; official_url=https://s26.q4cdn.com/656283129/files/doc_financials/2026/q2/v2/Airbnb-Q2-2026-Shareholder-Letter.pdf; artifact_path=data/filings/ABNB.US/Airbnb-Q2-2026-Shareholder-Letter.pdf; artifact_sha256=913155a2c62ffcd038aa42fee57c8ca84d7ac5e26d4fe395240a64100d880961; page=11; quote="Nights and Seats Booked grew 10% year-over-year ... GBV was $27.2 billion."

`S3-Q2-AI`: source_type=issuer_pdf; official_url=https://s26.q4cdn.com/656283129/files/doc_financials/2026/q2/v2/Airbnb-Q2-2026-Shareholder-Letter.pdf; artifact_path=data/filings/ABNB.US/Airbnb-Q2-2026-Shareholder-Letter.pdf; artifact_sha256=913155a2c62ffcd038aa42fee57c8ca84d7ac5e26d4fe395240a64100d880961; page=5; quote="Nearly 45% of issues ... are now resolved without a human agent."
