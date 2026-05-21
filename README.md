# Recruitment Matching Tool

A clinical trial recruitment aid that identifies which candidates from a pool best balance an enrolled cohort, and generates ideal "prototype" profiles when the pool is insufficient.

---

## Features

- Scores patient/control imbalance across age (SMD), sex (TVD), and BMI (SMD)
- Greedily selects candidates from a pool to maximally improve balance
- Generates prototype profiles when no real candidates remain
- Configurable dimension weights and recruitment targets
- GUI (Tkinter) and CLI interfaces
- Saves reports as plain text

---

## Requirements

- Python 3.13+ (It probably works on some earlier versions, I just didn't test it - feel free to try)
- `pandas`
- `numpy`

Install dependencies:

```bash
pip install pandas numpy
```

---

## CSV Format

Both the **enrolled** and **pool** files must be CSVs with these columns:

| Column | Description | Accepted values |
|--------|-------------|-----------------|
| `id` | Participant identifier | Any string |
| `type` | Role in trial | `patient`, `control` |
| `age` | Age in years | Numeric |
| `sex` | Biological sex | `M`, `F`, `X` (see normalisation below) |
| `bmi` | Body mass index | Numeric |

**Sex normalisation:** The tool accepts a range of input formats, including `MALE`/`FEMALE`, `W`, `D`, `NON-BINARY`, `NB`, `1`/`2`, and German variants (`männlich`, `weiblich`, `divers`). These are all mapped to `M`, `F`, or `X`.

**Type normalization:** For type: `patient`/`control`, `P`/`C`, `Gesund`/`Krank`, `G`/`K` are all accepted.

Rows with missing or unrecognisable values are skipped with a warning.

---

## GUI Usage

Run the graphical interface:

```bash
python recruitment_app.py
```

1. **Load File: Enrolled** — select your currently enrolled participants CSV.
2. **Load File: Pool** — optionally select a pool of candidates to recruit from. If omitted, the tool runs in prototype-only mode.
3. Configure settings:
   - **w_age / w_gender / w_bmi** — imbalance weights (should sum to 1.0; defaults: 0.4 / 0.4 / 0.2).
   - **N Patients / N Controls** — recruitment target.
   - **New / Max** — whether the target is the number of *new* recruits, or the *maximum total* enrolled after recruitment.
4. Click **Run**. Results appear in the text area.
5. Click **Save** to write the report to a `.txt` file.

---

## CLI Usage

```bash
python matching.py [OPTIONS]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--enrolled FILE` | CSV of currently enrolled participants | required |
| `--pool FILE` | CSV of available candidates | optional |
| `--n-patients INT` | Recruitment target for patients | auto |
| `--n-controls INT` | Recruitment target for controls | auto |
| `--mode max\|new` | Interpret targets as max total (`max`) or number of new recruits (`new`) | `max` |
| `--weights AGE SEX BMI` | Imbalance weights, must sum to 1.0 | `0.4 0.4 0.2` |
| `--out FILE` | Save report to file | none |
| `--demo` | Run with built-in demo data | — |

### Examples

```bash
# Recruit from a pool, aiming for 100 patients and 100 controls total
python matching.py --enrolled enrolled.csv --pool pool.csv --n-patients 100 --n-controls 100

# Recruit 10 new controls (no pool — prototype mode)
python matching.py --enrolled enrolled.csv --n-controls 10 --mode new

# Try it out with built-in demo data
python matching.py --demo
```

---

## How It Works

### Imbalance Score

The tool computes a weighted aggregate imbalance between the patient and control groups:

- **Age** — pooled standardised mean difference (SMD)
- **Sex** — total variation distance (TVD) between sex distributions
- **BMI** — pooled SMD

```
Aggregate = w_age × SMD(age) + w_sex × TVD(sex) + w_bmi × SMD(bmi)
```

Balance is rated **GOOD** (< 0.10), **MODERATE** (< 0.20), or **POOR** (≥ 0.20).

### Candidate Selection

Candidates are selected greedily from the pool. At each step, the tool picks whichever available candidate reduces the aggregate imbalance the most, until the recruitment targets are met or the pool is exhausted.

### Prototype Generation

If the pool is exhausted before targets are reached, the tool generates synthetic **prototype** profiles — descriptions of the age, sex, and BMI characteristics that would best rebalance the cohort. These are not real participants; they are recruitment targets to guide outreach.