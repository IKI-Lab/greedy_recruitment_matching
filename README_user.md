# Recruitment Matching Tool — User Guide

This tool helps you select candidates from a recruitment pool to best balance your enrolled trial cohort across age, sex, and BMI.

---

## Quick Start

1. Click **Load File: Enrolled** and select your enrolled participants file.
2. Click **Load File: Pool** and select your candidate pool file. *(Optional — see below.)*
3. Adjust settings if needed (defaults are usually fine).
4. Click **Run**.
5. Click **Save** to export the report as a `.txt` file.

---

## Input Files

Both files must be **CSV files** with the following columns:

| Column | Description |
|--------|-------------|
| `id` | Participant ID |
| `type` | `patient` or `control` |
| `age` | Age in years |
| `sex` | `M`, `F`, or `X` |
| `bmi` | BMI |

Sex values are flexible — `MALE`/`FEMALE`, `W`, `D`, `männlich`/`weiblich` etc. are all accepted.

Rows with missing or unrecognisable values are skipped automatically, and you will see a warning in the output.

---

## Settings

**Weights (w_age / w_gender / w_bmi):** How much each dimension counts toward the imbalance score. They should sum to 1.0. The defaults (0.4 / 0.4 / 0.2) work well for most trials.

**N Patients / N Controls:** Your recruitment target — interpreted differently depending on the mode selected:

- **Max** — the *total* number of patients/controls you want enrolled after recruitment (e.g. set 100 to recruit up to 100 total).
- **New** — the number of *additional* recruits to find on top of those already enrolled.

---

## Output

The report shows:

- **Current balance** — a summary table comparing patients and controls at baseline, with imbalance scores for age, sex, and BMI.
- **Selected candidates** — a ranked list of candidates drawn from the pool, in the order they were selected.
- **Balance after pool** — updated balance once pool candidates are added.
- **Prototypes** — if the pool is exhausted before the target is reached, the tool generates example profiles describing the *type* of recruit that would best rebalance the cohort. These are not real people — they are a guide for further outreach.

---

## No Pool File?

If you do not load a pool file, the tool runs in **prototype-only mode** and skips straight to generating ideal recruit profiles based on your enrolled cohort.
