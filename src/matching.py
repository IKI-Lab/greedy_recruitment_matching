"""
trial_matcher.py — Clinical trial recruitment matching tool

CSV format (enrolled and pool files):
  id, type (patient/control), age, sex (M/F/X), bmi

  Accepted sex values: M, F, X (also normalised: MALE→M, FEMALE→F,
  DIVERSE/NON-BINARY/NB/D/OTHER→X, numeric 1→M, 2→F)

Optional flags:
  --n-patients INT      Target number of additional patients  (default: auto from balance)
  --n-controls INT      Target number of additional controls  (default: auto from balance)
  --center LABEL        Label printed in report header (e.g. "Center A")
  --out FILE            Save report to a text file as well as printing it
  --weights AGE SEX BMI Imbalance weights, must sum to 1 (default: 0.4 0.4 0.2)
  --demo                Use built-in demo data
"""

import argparse
import io
import math
import sys
import tempfile
import textwrap
import contextlib
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIDTH = 72
REQUIRED_COLS = {"id", "type", "age", "sex", "bmi"}


# ---------------------------------------------------------------------------
# Sex normalisation
# ---------------------------------------------------------------------------

# Canonical categories used throughout
SEX_CATEGORIES = ["M", "F", "X"]
SEX_LABELS     = {"M": "Male", "F": "Female", "X": "Diverse/X"}

_SEX_MAP = {
    "M": "M", "MALE": "M", "1": "M", "männlich": "M", "MÄNNLICH": "M",
    "F": "F", "FEMALE": "F", "2": "F", "W": "F", "weiblich": "F", "WEIBLICH": "F",
    "X": "X", "D": "X", "DIVERSE": "X", "divers": "X",
    "NON-BINARY": "X", "NONBINARY": "X", "NB": "X",
    "OTHER": "X", "3": "X", "INTER": "X", "INTERSEX": "X",
}

def _normalise_sex(raw: str) -> str:
    return _SEX_MAP.get(raw.upper().strip(), raw)   # unknown values pass through and are filtered later


# ---------------------------------------------------------------------------
# Loading & validation
# ---------------------------------------------------------------------------

def load_csv(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise ValueError(f"ERROR reading {path}: {e}")

    df.columns = df.columns.str.strip().str.lower()
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"ERROR: {path} is missing columns: {', '.join(sorted(missing))}")

    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["bmi"] = pd.to_numeric(df["bmi"], errors="coerce")
    df["sex"]  = df["sex"].astype(str).str.strip().str.upper().map(_normalise_sex)
    df["type"] = df["type"].astype(str).str.strip().str.lower()
    df["id"]   = df["id"].astype(str).str.strip()

    # Complete-case analysis
    n_before = len(df)
    df = df.dropna(subset=["age", "bmi"])
    df = df[df["sex"].isin(["M", "F", "X"])]
    df = df[df["type"].isin(["patient", "control"])]
    dropped = n_before - len(df)
    if dropped:
        print(f"  Warning: {dropped} row(s) in {path} skipped (invalid/missing values)")
    if df.empty:
        raise ValueError(f"ERROR: no valid rows in {path}")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Imbalance scoring
# ---------------------------------------------------------------------------

def smd(a: pd.Series, b: pd.Series) -> float:
    """Pooled standardised mean difference."""
    n_a = len(a)
    n_b = len(b)
    if n_a < 2 or n_b < 2:
        return 0.0
    var_a = a.var(ddof=1)
    var_b = b.var(ddof=1)
    pooled_sd = math.sqrt(
        ((n_a - 1)*var_a + (n_b - 1)*var_b) / (n_a + n_b - 2)
    )
    if pooled_sd == 0 or np.isnan(pooled_sd):
        return 0.0
    return abs(a.mean() - b.mean()) / pooled_sd if pooled_sd > 0 else 0.0


def sex_tvd(a: pd.Series, b: pd.Series) -> float:
    """
    Total Variation Distance between sex distributions of two groups.
    TVD = 0.5 * sum |p_k - q_k| over categories {M, F, X}.
    Ranges [0, 1]; 0 = identical distributions.
    Works correctly with 2 or 3 categories — binary case reduces to |p_M - q_M|.
    """
    p = a.value_counts(normalize=True).reindex(SEX_CATEGORIES, fill_value=0)
    q = b.value_counts(normalize=True).reindex(SEX_CATEGORIES, fill_value=0)
    return float(0.5 * (p - q).abs().sum())


def sex_proportions(group: pd.Series) -> dict:
    """Return {cat: proportion} for all SEX_CATEGORIES."""
    counts = group.value_counts(normalize=True).reindex(SEX_CATEGORIES, fill_value=0)
    return counts.to_dict()


def imbalance(
    patients: pd.DataFrame,
    controls: pd.DataFrame,
    weights: Tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> dict:
    w_age, w_sex, w_bmi = weights
    age_smd  = smd(patients["age"], controls["age"])
    bmi_smd  = smd(patients["bmi"], controls["bmi"])
    tvd      = sex_tvd(patients["sex"], controls["sex"])
    total    = w_age * age_smd + w_sex * tvd + w_bmi * bmi_smd
    return dict(
        age=age_smd, sex=tvd, bmi=bmi_smd, total=total,
        p_sex=sex_proportions(patients["sex"]),
        c_sex=sex_proportions(controls["sex"]),
    )


def balance_label(total: float) -> str:
    if total < 0.10: return "GOOD"
    if total < 0.20: return "MODERATE"
    return "POOR"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def hline(char="─") -> str:
    return char * WIDTH

def bar(value: float, width: int = 28) -> str:
    filled = min(width, round(min(1.0, value / 1.2) * width))
    return "█" * filled + "░" * (width - filled)

def fmt_flag(val, thresholds):
    return "✓" if val < thresholds[0] else ("~" if val < thresholds[1] else "✗")

def fmt_balance(
    patients: pd.DataFrame,
    controls: pd.DataFrame,
    weights: tuple,
    label: str = "Current balance",
) -> str:
    sc  = imbalance(patients, controls, weights)
    lbl = balance_label(sc["total"])
    sym = {"GOOD": "✓", "MODERATE": "~", "POOR": "✗"}[lbl]

    lines = [f"\n  {label}  [{sym} {lbl}]", ""]
    lines.append(f"  {'':22}  {'Patients':>10}  {'Controls':>10}")
    lines.append(f"  {'N':22}  {len(patients):>10}  {len(controls):>10}")
    if len(patients) and len(controls):
        lines.append(f"  {'Mean age (yrs)':22}  {patients['age'].mean():>10.1f}  {controls['age'].mean():>10.1f}")
        lines.append(f"  {'SD age':22}  {patients['age'].std():>10.1f}  {controls['age'].std():>10.1f}")
        for cat in SEX_CATEGORIES:
            lbl = SEX_LABELS[cat] + " %"
            pv  = sc["p_sex"][cat] * 100
            cv  = sc["c_sex"][cat] * 100
            # Only show row if at least one group has >0 in this category
            if pv > 0 or cv > 0:
                lines.append(f"  {lbl:22}  {pv:>9.0f}%  {cv:>9.0f}%")
        lines.append(f"  {'Mean BMI':22}  {patients['bmi'].mean():>10.1f}  {controls['bmi'].mean():>10.1f}")
        lines.append("")
        lines.append(f"  {'Dimension':<14}  {'Value':>8}  {'':2}  Bar")
        lines.append(f"  {'─'*14}  {'─'*8}  {'─'*2}  {'─'*28}")
        lines.append(f"  {'Age (SMD)':<14}  {sc['age']:>8.3f}  {fmt_flag(sc['age'],(0.30,0.70)):>2}  {bar(sc['age'])}")
        lines.append(f"  {'Sex (TVD)':<14}  {sc['sex']:>8.3f}  {fmt_flag(sc['sex'],(0.10,0.20)):>2}  {bar(sc['sex']/0.5)}")
        lines.append(f"  {'BMI (SMD)':<14}  {sc['bmi']:>8.3f}  {fmt_flag(sc['bmi'],(0.30,0.70)):>2}  {bar(sc['bmi'])}")
        lines.append(f"  {'─'*14}  {'─'*8}")
        lines.append(f"  {'Aggregate':<14}  {sc['total']:>8.3f}  (weighted)")
    else:
        lines.append("  (insufficient data for one or both groups)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Greedy candidate scoring
# ---------------------------------------------------------------------------

def greedy_sequential(
    patients: pd.DataFrame,
    controls: pd.DataFrame,
    pool_pat: pd.DataFrame,
    pool_ctl: pd.DataFrame,
    n_patients: int,
    n_controls: int,
    weights: tuple,
    early_stop: bool = True,
) -> list:
    """
    TODO: Update description
    Joint sequential greedy search over both pools simultaneously.
 
    At each step, every remaining candidate in both pools is evaluated.
    The one whose addition most reduces the composite imbalance score is
    selected, subject to per-role caps (n_patients, n_controls).
 
    If early_stop is True (default), the search halts as soon as no
    candidate improves balance — i.e. the best available move would make
    things worse or leave them unchanged. Pass --no-early-stop to disable.
 
    Returns list of dicts, one per selection, in selection order:
      role, id, age, sex, bmi, improvement, score_after
    """
    cur_pat = patients.copy()
    cur_ctl = controls.copy()
    remaining = {
        "patient": pool_pat.copy().reset_index(drop=True),
        "control": pool_ctl.copy().reset_index(drop=True),
    }
    caps = {"patient": n_patients, "control": n_controls}
    counts = {"patient": 0, "control": 0}
    selected = []
 
    while True:
        # Check if all caps reached or both pools exhausted
        if all(counts[r] >= caps[r] or remaining[r].empty for r in ("patient", "control")):
            break
 
        current_score = imbalance(cur_pat, cur_ctl, weights)["total"]
        best = None  # will hold (score_after, improvement, role, idx, row)
 
        for role in ("patient", "control"):
            if counts[role] >= caps[role] or remaining[role].empty:
                continue
            for idx, cand in remaining[role].iterrows():
                row = cand.to_frame().T
                if role == "control":
                    score_after = imbalance(cur_pat, pd.concat([cur_ctl, row], ignore_index=True), weights)["total"]
                else:
                    score_after = imbalance(pd.concat([cur_pat, row], ignore_index=True), cur_ctl, weights)["total"]
                improvement = score_after - current_score       # Lower is better for SMD
                if best is None or score_after < best[0]:
                    best = (score_after, improvement, role, idx, cand)
 
        if best is None:
            break
 
        score_after, improvement, role, idx, cand = best
 
        if early_stop and improvement >= 0:
            print("Early stopping: No further improvement found")
            break
 
        # Commit selection
        selected.append({
            "step":        len(selected) + 1,
            "role":        role,
            "id":          cand["id"],
            "age":         cand["age"],
            "sex":         cand["sex"],
            "bmi":         cand["bmi"],
            "improvement": improvement,
            "score_after": score_after,
        })
        counts[role] += 1
        row_df = cand.to_frame().T
 
        if role == "control":
            cur_ctl = pd.concat([cur_ctl, row_df], ignore_index=True)
        else:
            cur_pat = pd.concat([cur_pat, row_df], ignore_index=True)
 
        remaining[role] = remaining[role].drop(index=idx).reset_index(drop=True)
 
    return selected, cur_pat, cur_ctl, counts


def fmt_selection_table(selected: list) -> str:
    if not selected:
        return "  (no candidates selected)"
    lines = ["\n Selected from pool:", ""]
    lines.append(
        f"  {'Step':>4}  {'Role':<9}  {'ID':<14}  {'Age':>5}  {'Sex':>5}  "
        f"{'BMI':>6}  {'Improvement':>12}  {'Score after':>11}"
    )
    lines.append(
        f"  {'─'*4}  {'─'*9}  {'─'*14}  {'─'*5}  {'─'*5}  "
        f"{'─'*6}  {'─'*12}  {'─'*11}"
    )
    for s in selected:
        flag = "▲" if s["improvement"] > 0.005 else ("≈" if s["improvement"] >= -0.005 else "▼")
        lines.append(
            f"  {s['step']:>4}  {s['role']:<9}  {s['id']:<14}  {s['age']:>5.1f}  "
            f"{s['sex']:>5}  {s['bmi']:>6.1f}  "
            f"{s['improvement']:>+12.4f}  {s['score_after']:>11.4f}  {flag}"
        )
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Prototype generation
# ---------------------------------------------------------------------------

def make_prototypes(
    patients: pd.DataFrame,
    controls: pd.DataFrame,
    n: int,
    role: str,          # "control" or "patient"
    weights: tuple,
) -> Tuple[str, str]:
    """
    Build n prototype profiles for the given role.
    The 'reference' is the group being matched TO; 'existing' is the group
    being recruited into.
    """
    reference = patients if role == "control" else controls
    existing  = controls if role == "control" else patients

    if len(reference) == 0:
        return f"  Cannot generate {role} prototypes — reference group is empty.\n", ""

    ref_male   = (reference["sex"] == "M").mean()
    ex_male    = (existing["sex"] == "M").mean() if len(existing) else 0.0
    ref_age_m  = reference["age"].mean()
    ref_age_sd = reference["age"].std() if len(reference) > 1 else 5.0
    ref_bmi_m  = reference["bmi"].mean()
    ref_bmi_sd = reference["bmi"].std() if len(reference) > 1 else 2.0
    ex_age_m   = existing["age"].mean() if len(existing) else ref_age_m
    ex_bmi_m   = existing["bmi"].mean() if len(existing) else ref_bmi_m
    ne         = len(existing)

    # Solve for target mean of new recruits to pull overall mean to reference
    if ne + n > 0:
        target_age = (ref_age_m * (ne + n) - ex_age_m * ne) / n
        target_bmi = (ref_bmi_m * (ne + n) - ex_bmi_m * ne) / n
    else:
        target_age, target_bmi = ref_age_m, ref_bmi_m

    target_age = float(np.clip(target_age, 18, 85))
    target_bmi = float(np.clip(target_bmi, 16, 50))

    # Sex split needed
    n_male_target   = round(ref_male * (ne + n)) - round(ex_male * ne)
    n_male_target   = int(np.clip(n_male_target, 0, n))
    n_female_target = n - n_male_target

    # Spread ages evenly across ±0.6 SD to represent realistic variety
    offsets = np.linspace(-0.6, 0.6, n) * ref_age_sd if n > 1 else np.array([0.0])

    profiles = []
    for i in range(n):
        sex = "M" if i < n_male_target else "F"
        age = int(np.clip(round(target_age + offsets[i]), 18, 85))
        bmi_off = ((i % 3) - 1) * ref_bmi_sd * 0.2
        bmi = round(float(np.clip(target_bmi + bmi_off, 16, 50)), 1)
        profiles.append({
            "rank":      i + 1,
            "sex":       sex,
            "age":       age,
            "age_range": f"{max(18, age-4)}–{min(85, age+4)}",
            "bmi":       bmi,
            "bmi_range": f"{max(16.0, bmi-2.0):.1f}–{min(50.0, bmi+2.0):.1f}",
            "priority":  "HIGH" if i < 3 else "normal",
        })

    summary = (
        f"  Recruit {n_male_target}M + {n_female_target}F {role}s  |  "
        f"target age ≈ {target_age:.0f} yrs (±{ref_age_sd:.0f})  |  "
        f"target BMI ≈ {target_bmi:.1f} (±{ref_bmi_sd:.1f})"
    )

    lines = []
    lines.append(f"  {'#':>3}  {'Sex':<7}  {'Age':>5}  {'Age range':>10}  "
                 f"{'BMI':>6}  {'BMI range':>12}  {'Priority':>8}")
    lines.append(f"  {'─'*3}  {'─'*7}  {'─'*5}  {'─'*10}  {'─'*6}  {'─'*12}  {'─'*8}")
    for p in profiles:
        sex_str = "Male" if p["sex"] == "M" else "Female"
        lines.append(f"  {p['rank']:>3}  {sex_str:<7}  {p['age']:>5}  "
                     f"{p['age_range']:>10}  {p['bmi']:>6.1f}  "
                     f"{p['bmi_range']:>12}  {p['priority']:>8}")
    return summary, "\n".join(lines)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(
    enrolled_path: str,
    pool_path: Optional[str],
    n_patients: Optional[int],
    n_controls: Optional[int],
    max_patients: Optional[int],
    max_controls: Optional[int],
    weights: tuple,
    silent:bool = False,
) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        enrolled = load_csv(enrolled_path)
        pool = load_csv(pool_path) if pool_path is not None else None
    patients = enrolled[enrolled["type"] == "patient"].copy()
    controls = enrolled[enrolled["type"] == "control"].copy()
    pool_pat = pool[pool["type"] == "patient"].copy() if pool is not None else None
    pool_ctl = pool[pool["type"] == "control"].copy() if pool is not None else None 

    if n_controls is None:
        if max_controls:
            n_controls = max(0, max_controls- len(controls))
        else:
            n_controls = max(1, len(patients) - len(controls))
    if n_patients is None:
        if max_patients:
            n_patients = max(0, max_patients - len(patients))
        else:
            n_patients = max(1, len(controls) - len(patients))

    def w(s):
        line = s + "\n"
        out.write(line)
        if not silent:
            print(s, flush=True)

    w(hline("="))
    w(" TRIAL RECRUITMENT MATCHING TOOL")
    w(hline("="))
    w(f" weigths - age: {weights[0]}, gender: {weights[1]}, bmi {weights[2]}")
    w(fmt_balance(patients, controls, weights, "Current balance"))
    w(hline("="))
    w(f" Selecting: {n_patients} patients and {n_controls} controls")

    remaining_pat = n_patients
    remaining_ctl = n_controls
    if pool is not None:
        w(f" Starting search from pool...")
        selected, cur_pat, cur_ctl, counts = greedy_sequential(
            patients, controls, pool_pat, pool_ctl, n_patients, n_controls, 
            weights, early_stop=False
        )
        patients, controls = cur_pat, cur_ctl
        remaining_pat -= counts["patient"]
        remaining_ctl -= counts["control"]
        w(f" Found {counts['patient']} patients and {counts['control']} controls.")
        w(f" Patients remaining: {remaining_pat}. Controls remaining: {remaining_ctl}.")
        w(hline("="))
        w(fmt_selection_table(selected))
        w(hline("="))
        w(fmt_balance(cur_pat, cur_ctl, weights, "Balance after drawing from pool"))
        w(hline("="))
    else:
        w(" No pool provided, skipping to prototypes.")
        w(hline("="))
        

    if remaining_pat:
        w(f"\n Not enough patients found in pool - Creating {remaining_pat} patient prototypes:")
        w(" (The following list does not contain real patients, but examples of optimal patients to rebalance the distribution)\n")
        proto_pat_summary, proto_pat_description = make_prototypes(
            patients, controls, remaining_pat, "patient", weights)
        w(proto_pat_summary)
        w(proto_pat_description)

    if remaining_ctl:
        w(f"\n Not enough controls found in pool - Creating {remaining_ctl} control prototypes:")
        w(" (The following list does not contain real controls, but examples of optimal controls to rebalance the distribution)\n")
        proto_ctl_summary, proto_ctl_description = make_prototypes(
            patients, controls, remaining_ctl, "control", weights)
        w(proto_ctl_summary)
        w(proto_ctl_description)
        
 

    return out.getvalue()
    
# ---------------------------------------------------------------------------
# Demo data  (pool includes both patients and controls)
# ---------------------------------------------------------------------------

DEMO_ENROLLED = """id,type,age,sex,bmi
P01,patient,58,M,27.2
P02,patient,62,M,29.1
P03,patient,45,F,24.8
P04,patient,71,M,31.0
P05,patient,54,F,28.3
P06,patient,67,M,30.2
P07,patient,49,M,26.5
P08,patient,73,F,25.9
P09,patient,60,M,27.8
P10,patient,55,M,28.9
C01,control,42,F,23.1
C02,control,38,F,22.8
C03,control,44,F,24.2
C04,control,61,M,26.8
C05,control,39,F,21.9
C06,control,47,F,25.0
"""

DEMO_POOL = """id,type,age,sex,bmi
X01,control,58,M,28.1
X02,control,63,M,29.5
X03,control,40,F,23.0
X04,control,70,M,30.8
X05,control,55,M,27.2
X06,control,52,M,26.9
X07,control,66,F,25.7
X08,control,59,M,28.8
X09,control,48,F,24.5
X10,control,72,M,31.2
X11,control,57,M,27.5
X12,control,64,M,29.0
X13,control,35,F,22.1
X14,control,53,M,26.3
X15,control,69,M,30.1
XP1,patient,44,F,25.3
XP2,patient,68,M,30.5
XP3,patient,57,M,28.0
XP4,patient,51,F,26.2
XP5,patient,65,M,29.8
"""

def _write_demo(content: str, prefix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", prefix=prefix + "_", delete=False
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Clinical trial recruitment matching tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python trial_matcher.py pool  --enrolled enrolled.csv --pool pool.csv
              python trial_matcher.py proto --enrolled enrolled.csv
              python trial_matcher.py pool  --demo
              python trial_matcher.py proto --demo --n-controls 8 --n-patients 4 --new
        """),
    )
    parser.add_argument("--enrolled",   help="CSV of currently enrolled participants")
    parser.add_argument("--pool",       help="CSV of available candidates")
    parser.add_argument("--n-patients", type=int, default=None,
                        dest="n_patients",
                        help="Number of additional patients to target")
    parser.add_argument("--n-controls", type=int, default=None,
                        dest="n_controls",
                        help="Number of additional controls to target")
    parser.add_argument("--out",        default=None, help="Save report to file")
    parser.add_argument("--weights",    type=float, nargs=3, default=[0.4, 0.4, 0.2],
                        metavar=("AGE", "SEX", "BMI"))
    parser.add_argument("--demo",       action="store_true")
    parser.add_argument("--mode",       default="max", help="Toggle to set number arguments as numer of new reruits 'new', or max number of recruits 'max'.")
    args = parser.parse_args()

    weights = tuple(args.weights)
    if abs(sum(weights) - 1.0) > 0.01:
        sys.exit(f"ERROR: weights must sum to 1.0 (got {sum(weights):.3f})")

    if args.demo:
        # Create temporary files
        enrolled_path = _write_demo(DEMO_ENROLLED, "demo_enrolled")
        pool_path     = _write_demo(DEMO_POOL, "demo_pool")
        print(f"  [demo] enrolled : {enrolled_path}")
        print(f"  [demo] pool     : {pool_path}\n")
    else:
        if not args.enrolled:
            sys.exit("ERROR: --enrolled is required (or use --demo)")
        enrolled_path = args.enrolled
        pool_path     = args.pool

    if not pool_path:
        print("No pool passed, running fully in prototype mode.")
    
    if args.mode == "new":
        report = run(enrolled_path, pool_path, args.n_patients, args.n_controls, None, None, weights)
    elif args.mode == "max":
        report = run(enrolled_path, pool_path, None, None, args.n_patients, args.n_controls, weights)
    else:
        raise ValueError(f"Invalid value for argument 'mode': {args.mode}")
    print(report)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"  Report saved to: {args.out}")

    if args.demo:
        import os
        os.unlink(enrolled_path)
        os.unlink(pool_path)


if __name__ == "__main__":
    main()