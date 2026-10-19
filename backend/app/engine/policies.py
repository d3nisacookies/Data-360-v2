"""Rules & policies checklist. Each memo compliance check maps to one rule; switching a rule
off removes its checks from the memo and the draft decision. Sample set for a Singapore-booked
credit memo: thresholds and applicability to be confirmed with the bank's Credit Risk and Compliance."""
import re

POLICY_GROUPS = [
    ["Credit authority and approval", [
        ["A1", "Delegated credit authority", "Who can approve what size or grade (RM, Credit Officer, Head of Credit, CRO delegate, Committee)", "Bank credit authority matrix"],
        ["A2", "Four-eyes and independence", "Business proposes; independent Credit Risk reviews and approves", "Credit policy; MAS credit risk management guidelines"],
        ["A3", "Committee referral triggers", "Weak grade, large exposure, policy exception, watchlist or related party go to Credit Committee", "Credit policy"],
        ["A4", "Annual review", "Every borrower reviewed at least every 12 months; more often if on the watchlist", "Credit policy; MAS Notice 612"],
        ["A5", "Conditions precedent and subsequent", "Listed, tracked and evidenced before drawdown", "Credit procedures"],
        ["A6", "Policy exception approval", "Breaches need a documented exception, approved one level up, with an expiry date", "Credit policy"]]],
    ["Credit policy and risk appetite", [
        ["P1", "Minimum internal rating", "No new or increased lending below grade 6 without referral", "Risk appetite"],
        ["P2", "Rating override governance", "Internal vs external rating gaps and manual overrides justified and approved", "Rating policy"],
        ["P3", "Industry and sector appetite", "Restricted or watch sectors; sector caps", "Risk appetite statement"],
        ["P4", "Country risk limits", "Country limits and transfer risk for cross-border lending", "Country risk policy"],
        ["P5", "Maximum tenor", "Remaining tenor of 7 years or less by product", "Credit policy"],
        ["P6", "Pricing discipline", "Pricing above cost of funds; RAROC above hurdle unless justified", "Pricing and ALM policy"],
        ["P7", "Leverage limits", "Maximum net debt / EBITDA by product", "Credit policy; leveraged lending guidance"],
        ["P8", "Structured and leveraged finance standards", "Sponsor quality, equity contribution, covenant package", "Product policy"]]],
    ["Rating, staging and provisioning", [
        ["R1", "Credit grading", "Every borrower graded on approved models; grades map to regulatory categories", "MAS Notice 612"],
        ["R2", "Loan classification", "Pass, special mention, substandard, doubtful, loss", "MAS Notice 612"],
        ["R3", "Impairment staging", "IFRS 9 stage 1/2/3 and significant-increase-in-credit-risk triggers", "IFRS 9 / SFRS(I) 9 or group accounting standard"],
        ["R4", "Default definition", "90+ days past due or unlikely to pay", "Basel; accounting policy"],
        ["R5", "Restructured loans", "Forbearance flagged and reclassified", "MAS Notice 612; credit policy"],
        ["R6", "Watchlist and early warning", "Triggers for watchlist entry and required actions", "Credit monitoring policy"]]],
    ["Exposure limits and concentration", [
        ["E1", "Large exposure / single counterparty group", "Exposure below 25% of Tier 1 capital; connected parties grouped", "MAS large-exposure rules / Basel (confirm branch applicability)"],
        ["E2", "Related-party lending", "Arm's-length terms and approval for related parties", "MAS related-party requirements; group policy"],
        ["E3", "Portfolio concentration", "Top-20 obligor, sector and country concentration", "Risk appetite"],
        ["E4", "Group limit consolidation", "Facilities across group entities counted against one group limit", "Group credit policy"]]],
    ["KYC, AML and sanctions", [
        ["K1", "Customer due diligence complete", "Approval blocked until KYC is complete and in date", "MAS Notice 626"],
        ["K2", "Beneficial ownership", "Owners at 25%+ identified and verified", "MAS Notice 626"],
        ["K3", "PEP screening", "Politically exposed persons identified; enhanced due diligence and senior approval", "MAS Notice 626"],
        ["K4", "Risk-based review frequency", "High-risk clients reviewed more often; reviews in date", "MAS Notice 626; AML policy"],
        ["K5", "Sanctions screening", "Borrower, guarantors, owners and counterparties screened against UN, MAS, OFAC, EU, UK and Japan lists", "MAS targeted financial sanctions; group sanctions policy"],
        ["K6", "Potential match clearance", "No approval until Financial Crime Compliance clears or confirms matches", "Sanctions policy"],
        ["K7", "Adverse media", "Negative news reviewed and recorded", "AML policy"],
        ["K8", "Tax transparency", "FATCA and CRS classification", "FATCA / CRS rules"]]],
    ["Legal and documentation", [
        ["L1", "Authority to borrow", "Board resolution, constitution check, authorised signatories", "Legal policy"],
        ["L2", "Executed facility documents", "Signed and complete before drawdown", "Credit administration procedures"],
        ["L3", "Security perfection", "Charges registered and filings made on time", "Legal and collateral policy"],
        ["L4", "Legal opinions", "Required for cross-border or new-jurisdiction deals", "Legal policy"],
        ["L5", "Standard clauses and deviations", "Change of control, sanctions and MAC clauses; deviations approved", "Documentation standards"],
        ["L6", "Litigation and insolvency", "Proceedings disclosed and assessed", "Credit policy"]]],
    ["Collateral, guarantees and covenants", [
        ["G1", "Eligible collateral and haircuts", "What counts as security and the haircut applied", "Collateral policy"],
        ["G2", "Valuation frequency", "Independent valuation at least annually; full valuation where LTV is high", "Collateral policy"],
        ["G3", "LTV limits", "Maximum LTV by asset type, with a cure mechanism", "Credit policy"],
        ["G4", "Guarantee validity", "Guarantor creditworthiness and expiry tracking", "Collateral policy"],
        ["G5", "Covenant monitoring", "Tested on schedule; breaches escalated; waivers approved", "Credit monitoring"],
        ["G6", "Insurance", "Required cover over secured assets", "Collateral policy"]]],
    ["ESG and environmental risk", [
        ["S1", "Environmental risk assessment", "E&S due diligence in credit decisions", "MAS Guidelines on Environmental Risk Management (banks)"],
        ["S2", "Equator Principles", "Category A/B/C review and ESIA for project finance", "Equator Principles"],
        ["S3", "Sector policies", "Restrictions such as coal and deforestation", "Group sector policies"],
        ["S4", "Climate and transition risk", "Transition and physical risk; financed emissions", "Group climate policy"]]],
    ["Risk data quality and reporting", [
        ["D1", "Risk data aggregation", "Accuracy, completeness, timeliness and adaptability of risk data", "BCBS 239"],
        ["D2", "Golden source for critical fields", "One authoritative value per field, reconciled across systems", "Data governance policy"],
        ["D3", "Data ownership", "Every source has an owner and steward", "Data governance policy"],
        ["D4", "Regulatory return mapping", "Fields map to MAS returns (e.g. MAS 610, 637)", "Regulatory reporting"],
        ["D5", "Identifiers", "LEI and registration numbers captured", "Regulatory reporting"]]],
    ["Records, confidentiality and data protection", [
        ["C1", "Credit file completeness", "Memo, approvals and evidence filed", "MAS Notice 612; credit administration"],
        ["C2", "Record retention", "Credit records kept for the minimum period after the facility ends", "Records policy"],
        ["C3", "Banking secrecy", "Customer information disclosed only as permitted", "Banking Act s.47"],
        ["C4", "Personal data protection", "Personal data of owners and signatories handled lawfully", "PDPA"],
        ["C5", "Inside information", "Wall-crossing and MNPI handling for deal data", "Conflicts and market conduct policy"]]],
    ["Models, technology and AI", [
        ["M1", "Model risk management", "Rating, early-warning and ECL models validated before use", "Model risk policy"],
        ["M2", "Use of AI in decisions", "AI drafts only; humans approve; fairness, explainability, monitoring", "MAS FEAT principles; MAS AI risk guidance"],
        ["M3", "Technology risk", "Access control, audit logs, resilience", "MAS Technology Risk Management Guidelines"],
        ["M4", "Outsourcing and third parties", "Vendor platforms and data providers assessed", "MAS outsourcing guidelines"]]],
    ["Conduct and conflicts", [
        ["X1", "Conflicts of interest", "Approver independence; interests declared", "Conduct policy"],
        ["X2", "Fair dealing", "Fair terms and pricing; no tying", "Conduct policy"],
        ["X3", "Individual accountability", "Named owners for each decision", "MAS individual accountability guidelines"]]],
]
POLICY = {r[0]: {"id": r[0], "t": r[1], "d": r[2], "src": r[3], "g": g} for g, rs in POLICY_GROUPS for r in rs}
ALL = list(POLICY)
TESTED = {"K1", "K2", "K3", "K4", "K5", "K6", "K7", "G3", "G5", "P1", "P2", "R3", "E1", "P6", "P5", "L6", "L1", "S2", "D1", "D2"}


def rule_of_check(c: str) -> str | None:
    if c == "KYC complete":
        return "K1"
    if c in ("KYC review in date", "AML risk rating"):
        return "K4"
    if c == "PEP screening":
        return "K3"
    if c == "UBO validated":
        return "K2"
    if c == "Adverse media":
        return "K7"
    if c == "Sanctions feed screening":
        return "K5"
    if c in ("Internal screening records", "Escalations open"):
        return "K6"
    if c == "LTV covenant":
        return "G3"
    if c.endswith(" covenant"):
        return "G5"
    if c.startswith("Rating floor"):
        return "P1"
    if c == "Internal vs external rating":
        return "P2"
    if c.startswith("Asset quality"):
        return "R3"
    if c.startswith("Large exposure"):
        return "E1"
    if c == "Pricing above cost of funds":
        return "P6"
    if c.startswith("Tenor"):
        return "P5"
    if c == "Litigation and insolvency":
        return "L6"
    if c in ("Authorised signatories", "Corporate authority"):
        return "L1"
    if c == "Equator Principles and ESIA":
        return "S2"
    if c == "Data confidence":
        return "D1"
    if c == "Critical fields reconciled":
        return "D2"
    return None


def catalogue() -> dict:
    return {"groups": [{"name": g, "rules": [POLICY[r[0]] for r in rs]} for g, rs in POLICY_GROUPS], "tested": sorted(TESTED)}


def clean_selection(ids) -> list[str]:
    return [i for i in dict.fromkeys(ids or []) if i in POLICY and re.fullmatch(r"[A-Z]\d", i)]
