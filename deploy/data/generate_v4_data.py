"""Generate the LensS v4 data pack: the October 2026 story (as of 20 October 2026).

    python deploy/data/generate_v4_data.py            # writes the v4 workbook
    python deploy/data/generate_v4_data.py --check    # prints the story figures, writes nothing

Reproducible: one seed, no other randomness. The v3 pack (LensS_Collections_Demo_Development_Pack.xlsx)
is the template: the same 20,000 accounts keep their static attributes (product, region, language,
income, vulnerability, dispute, strategy, channel, collector, driver), so every dimension value, ID
format and distribution shape is unchanged. Everything that describes the month is regenerated for
1-20 October 2026: arrears stage, balance, scores, contact attempts, contact, promises, payments, cost
and opportunity. The other 10 sheets are copied, with only their date text moved to October.

The story (README "v4 data"): about 55% of the monthly target collected with 65% of the month gone,
promises plentiful but ~40% of those already due broken, so promises due before month-end cover less
than the remaining gap (Target likelihood Low). The levers are real and sized: Personal Loan and Credit
Card 31-60 rolling forward, Kolkata hard to reach, Team F behind, Digital First over-contacting by SMS
with poor contact, a cluster of promises due in the next 7 days, disputed and vulnerable customers who
break promises. Acting on chapters 4-5 (save the promises at risk this week, work high-value and
priority accounts) is sized to close about the whole remaining gap: behind, but recoverable.

Every flag follows the workbook rules row by row: R04 matured = PTP_Due_Date <= Snapshot_Date; R05
broken = matured and Recovery_MTD < 90% of PTP_Amount; R06 cured = Recovery_MTD >= 90% of
Outstanding_Balance; roll forward/back = later/earlier bucket than Prior_DPD_Bucket; R10 RPC only when
attempted. Calibration targets are in CALIBRATION; the generator solves its free parameters to hit them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "raw_data"
TEMPLATE = DATA_DIR / "LensS_Collections_Demo_Development_Pack.xlsx"
OUTPUT = DATA_DIR / "LensS_Collections_V4_Data_Pack.xlsx"

SEED = 20261020
AS_OF = pd.Timestamp("2026-10-20")
MONTH_START = pd.Timestamp("2026-10-01")
MONTH_END = pd.Timestamp("2026-10-31")
DAYS_ELAPSED = (AS_OF - MONTH_START).days + 1          # 20
DAYS_IN_MONTH = MONTH_END.day                           # 31

CALIBRATION = {
    "achievement": 0.545,        # collected / monthly target (accounts in collections)
    "broken_share": 0.40,        # broken / promises already due (R05)
    "gap_coverage": 0.62,        # expected from promises / remaining gap: Low (< 1.0)
    "outlook_with_action": 0.98, # (outlook + upside from chapters 4-5) / target: most of the gap closed
}

# Rules the generator must agree with (workbook Business_Rules and gold.business_rules_config).
BROKEN_PCT = 0.90       # R05
CURE_PCT = 0.90         # R06
HIGH_RISK = 0.70        # R07
INTERVENTION_PROP = 0.25  # R08
Q_HIGH_PROP, Q_HIGH_BAL = 0.60, 100_000
Q_BREAK_PROP, Q_BREAK_RISK = 0.35, 0.60
Q_WINDOW = 7
PRIORITY_TOP = 100

BUCKETS = ["Current", "1-30", "31-60", "61-90", "91-180", "180+"]
ORDER = {b: i for i, b in enumerate(BUCKETS)}
DPD_RANGE = {"Current": (0, 0), "1-30": (1, 30), "31-60": (31, 60), "61-90": (61, 90), "91-180": (91, 180), "180+": (181, 360)}
CHANNELS = ["Voice", "WhatsApp", "SMS", "Email"]
COST_PER_ATTEMPT = np.array([24.0, 1.1, 0.35, 0.2])   # as in v3: Voice, WhatsApp, SMS, Email
FIELD_VISIT_COST = 180.0

# The levers (logit shifts unless noted). Kept small enough that no segment is absurd.
LAGGING = {("Personal Loan", "31-60"), ("Credit Card", "31-60")}
WEAK_TEAM = "Team F"
WEAK_COLLECTORS = {"COL053", "COL057", "COL060"}
HARD_REGION = "Kolkata"
OVER_CONTACT_STRATEGY = "Digital First"   # SMS-heavy, poor contact (R14)

STRATEGY_ATTEMPTS = {   # mean contact attempts in 20 days
    "Standard": 3.6, "Voice Intensive": 4.1, "Assisted Digital": 3.8,
    "Digital First": 6.4, "Vulnerability Care": 3.0, "Field Escalation": 3.8,
}
STRATEGY_MIX = {        # share of attempts by channel: Voice, WhatsApp, SMS, Email
    "Standard": [0.45, 0.20, 0.20, 0.15], "Voice Intensive": [0.70, 0.10, 0.10, 0.10],
    "Assisted Digital": [0.30, 0.35, 0.20, 0.15], "Digital First": [0.08, 0.17, 0.62, 0.13],
    "Vulnerability Care": [0.50, 0.20, 0.10, 0.20], "Field Escalation": [0.50, 0.15, 0.20, 0.15],
}
PREFERRED_BOOST = {"Voice": 0, "WhatsApp": 1, "SMS": 2, "Email": 3, "Digital Self-Cure": 2, "Field": 0}


def logistic(x):
    return 1.0 / (1.0 + np.exp(-x))


def bisect(f, lo, hi, target, iters=40, increasing=True):
    """x in [lo, hi] with f(x) ~= target, for monotone f."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class Pack:
    """The template's accounts plus every random draw, fixed once so calibration is deterministic."""

    def __init__(self, sheets: dict[str, pd.DataFrame], seed: int):
        self.sheets = sheets
        self.rng = rng = np.random.default_rng(seed)
        v3 = sheets["Fact_Collections_Snapshot"].copy().reset_index(drop=True)
        n = self.n = len(v3)
        self.v3 = v3
        u = lambda: rng.random(n)

        # --- arrears stage: September's stage moves on a month -------------------------------
        prior = v3["Prior_DPD_Bucket"].to_numpy(object).copy()
        bucket = v3["DPD_Bucket"].to_numpy(object).copy()
        dpd = v3["DPD"].to_numpy(int).copy()
        product = v3["Product"].to_numpy(object)
        strategy = v3["Treatment_Strategy"].to_numpy(object)
        r1, r2 = u(), u()
        lag_prod = np.isin(product, ["Personal Loan", "Credit Card"])
        # A worse month: more early-stage accounts roll forward, most of all Personal Loan and Credit Card.
        to_3160 = (bucket == "1-30") & (r1 < np.where(lag_prod, 0.30, 0.07))
        to_91 = (bucket == "61-90") & (r1 < 0.05)
        moved = to_3160 | to_91
        prior[to_3160], bucket[to_3160] = "1-30", "31-60"
        prior[to_91], bucket[to_91] = "61-90", "91-180"
        lo = np.array([DPD_RANGE[b][0] for b in bucket]); hi = np.array([DPD_RANGE[b][1] for b in bucket])
        jitter = rng.integers(-3, 4, n)
        dpd = np.where(moved, lo + np.floor(r2 * (hi - lo + 1)).astype(int), np.clip(dpd + jitter, lo, hi))
        self.prior, self.bucket, self.dpd = prior, bucket, dpd
        self.roll_fwd = np.array([ORDER[b] > ORDER[p] for b, p in zip(bucket, prior)]).astype(int)
        self.roll_back = np.array([ORDER[b] < ORDER[p] for b, p in zip(bucket, prior)]).astype(int)
        self.lagging = np.array([(p, b) in LAGGING for p, b in zip(product, bucket)])

        # --- balance: interest and fees accrue; rolled accounts grow more ---------------------
        bal = v3["Outstanding_Balance"].to_numpy(float) * np.exp(rng.normal(0.012, 0.035, n) + 0.025 * self.roll_fwd)
        self.bal = np.round(np.clip(bal, 2500.0, 549_999.0), 2)
        self.band = np.select([self.bal < 10_000, self.bal < 50_000, self.bal < 200_000], ["<10K", "10K-50K", "50K-200K"], ">200K")

        # --- scores: same shape as v3, risk a little higher in a worse month ------------------
        risk = v3["Nonpayment_Risk"].to_numpy(float)
        # An account that moved stage takes the risk of a v3 account already in that stage.
        for b in ("31-60", "91-180"):
            pool = v3.loc[v3["DPD_Bucket"] == b, "Nonpayment_Risk"].to_numpy(float)
            idx = np.where(moved & (bucket == b))[0]
            risk[idx] = rng.choice(pool, len(idx))
        risk = risk + rng.normal(0.015, 0.03, n) + 0.03 * self.roll_fwd + 0.04 * self.lagging
        self.risk = np.round(np.clip(risk, 0.01, 0.99), 4)
        prop = v3["Payment_Propensity"].to_numpy(float) + rng.normal(-0.01, 0.03, n)
        self.prop = np.round(np.clip(prop, 0.05, 0.65), 4)

        # --- contact attempts (20 days) ------------------------------------------------------
        region = v3["Region"].to_numpy(object); team = v3["Team"].to_numpy(object)
        collector = v3["Collector_ID"].to_numpy(object); channel = v3["Preferred_Channel"].to_numpy(object)
        vuln = v3["Vulnerability_Type"].notna().to_numpy(); dispute = v3["Dispute_Flag"].to_numpy(int)
        self.region, self.team, self.collector, self.channel, self.vuln, self.dispute = region, team, collector, channel, vuln, dispute
        self.product, self.strategy = product, strategy
        lam = np.array([STRATEGY_ATTEMPTS[s] for s in strategy]) * np.where(bucket == "180+", 0.85, 1.0)
        attempts = rng.poisson(lam)
        attempts[u() < 0.065] = 0                              # never attempted this month
        mix = np.array([STRATEGY_MIX[s] for s in strategy], float)
        pref = np.array([PREFERRED_BOOST[c] for c in channel])
        mix[np.arange(n), pref] *= 1.6
        mix /= mix.sum(1, keepdims=True)
        split = np.zeros((n, 4), int)
        for i in np.where(attempts > 0)[0]:
            split[i] = rng.multinomial(attempts[i], mix[i])
        self.attempts, self.split = attempts, split
        self.cost = np.round(split @ COST_PER_ATTEMPT + np.where(channel == "Field", FIELD_VISIT_COST, 0.0), 2)

        # --- collector effects: Team F behind, three collectors well behind --------------------
        ids = sorted(set(collector))
        ceff = dict(zip(ids, rng.normal(0, 0.15, len(ids))))
        self.coll = np.array([ceff[c] for c in collector]) + np.where(team == WEAK_TEAM, -0.35, 0) + np.isin(collector, list(WEAK_COLLECTORS)) * -0.45

        # --- reaching the customer (R10: only when attempted) ---------------------------------
        bucket_rpc = {"Current": 0.6, "1-30": 0.55, "31-60": 0.35, "61-90": 0.2, "91-180": -0.1, "180+": -0.9}
        x = (np.array([bucket_rpc[b] for b in bucket]) - 2.6 * (self.risk - 0.3)
             + np.where(region == HARD_REGION, -0.8, 0) + np.where(region == "Chennai", -0.12, 0)
             + np.select([channel == "Voice", channel == "SMS", channel == "Digital Self-Cure"], [0.25, -0.35, -0.2], 0)
             + np.select([strategy == OVER_CONTACT_STRATEGY, strategy == "Vulnerability Care", strategy == "Field Escalation"], [-0.45, -0.25, -0.3], 0)
             + 0.6 * self.coll + 0.15 * np.log1p(attempts) - 0.25)
        self.rpc = ((u() < logistic(x)) & (attempts > 0)).astype(int)
        # Contacted: the right party, or someone else at the number.
        self.contacted = np.where(self.rpc == 1, 1, ((attempts > 0) & (u() < 0.09)).astype(int))

        # --- promise to pay (after a right-party contact) -------------------------------------
        bucket_ptp = {"Current": 0.3, "1-30": 0.3, "31-60": 0.15, "61-90": -0.05, "91-180": -0.4, "180+": -1.2}
        x = (np.array([bucket_ptp[b] for b in bucket]) - 2.0 * (self.risk - 0.3) + 1.2 * (self.prop - 0.35)
             - 0.8 * dispute - 0.3 * vuln + 0.3 * self.coll)
        self.ptp = ((self.rpc == 1) & (u() < logistic(x))).astype(int)
        frac = 0.08 + 0.37 * rng.beta(2, 4, n)                  # promised share of the balance
        self.ptp_amt = np.where(self.ptp == 1, np.round(self.bal * frac, 2), 0.0)
        self.u_promise_day, self.u_lag = u(), u()

        # --- draws for outcomes ---------------------------------------------------------------
        self.u_keep, self.u_paid, self.u_zero, self.u_early, self.u_early_amt = u(), u(), u(), u(), u()
        self.u_np, self.u_np_amt, self.u_follow, self.u_follow_day, self.u_contact_day = u(), u(), u(), u(), u()
        self.u_keep_amt, self.u_opp = u(), u()
        # Honour propensity, without the intercept the calibration solves.
        prod_keep = {"Mortgage": 0.3, "Auto Loan": 0.15, "SME Loan": -0.1, "Credit Card": 0.0, "Personal Loan": 0.0}
        # The plan's view of a normal month: the book's structure (scores, product, disputes, vulnerability)...
        self.keep_x_plan = (3.0 * (self.prop - 0.35) - 2.2 * (self.risk - 0.3) + np.array([prod_keep[p] for p in product])
                            - 0.7 * dispute - 0.35 * vuln)
        # ...and this month's levers on top: what the plan didn't expect.
        self.keep_x = (self.keep_x_plan - 0.55 * self.lagging - 0.45 * self.roll_fwd - 0.25 * (region == HARD_REGION)
                       - 0.2 * (strategy == OVER_CONTACT_STRATEGY) + 0.9 * self.coll)
        bucket_np = {"Current": 0.08, "1-30": 0.07, "31-60": 0.05, "61-90": 0.04, "91-180": 0.025, "180+": 0.01}
        self.np_plan = np.array([bucket_np[b] for b in bucket])
        self.np_prob = (self.np_plan * np.where(team == WEAK_TEAM, 0.7, 1.0)
                        * np.where(region == HARD_REGION, 0.8, 1.0) * np.where(self.lagging, 0.6, 1.0))
        self.pnoise = {}

    # ------------------------------------------------------------------------------------------
    def outcomes(self, keep_c: float, skew: float) -> dict:
        """Promise timing, payments and flags for a kept-intercept and a promise-timing skew."""
        n = self.n
        ptp = self.ptp == 1
        # Promise taken on a contact day up to the snapshot (later in the month for skew > 1), due
        # 2-17 days on but always within October: the data stops at the month, nothing falls due in
        # November. A promise taken late in the month gets a shorter lag (at most to the 31st).
        promise_day = 1 + np.minimum(19, np.floor(20 * self.u_promise_day ** (1 / skew))).astype(int)
        lag_span = np.minimum(16, DAYS_IN_MONTH - 1 - promise_day)
        due_day = promise_day + 2 + np.floor(lag_span * self.u_lag).astype(int)
        due = np.where(ptp, due_day, -1)
        matured = ptp & (due <= DAYS_ELAPSED)
        upcoming = ptp & ~matured
        kept = matured & (self.u_keep < logistic(keep_c + self.keep_x))
        broken = matured & ~kept
        rec = np.zeros(n)
        rec[kept] = self.ptp_amt[kept] * (0.90 + 0.15 * self.u_keep_amt[kept])
        part = broken & (self.u_zero >= 0.45)                       # broken, but something paid
        rec[part] = self.ptp_amt[part] * (0.05 + 0.84 * self.u_paid[part])
        early = upcoming & (self.u_early < 0.08)                    # paid part before the due date
        rec[early] = self.ptp_amt[early] * (0.10 + 0.50 * self.u_early_amt[early])
        payer = ~ptp & (self.u_np < self.np_prob)                   # paid without a promise
        rec[payer] = self.bal[payer] * (0.02 + 0.10 * self.u_np_amt[payer])
        rec = np.round(np.minimum(rec, 0.85 * self.bal), 2)
        # R05 applied to the amounts exactly as stored (a kept promise is paid at least 90%).
        broken_flag = (matured & (rec < BROKEN_PCT * self.ptp_amt)).astype(int)
        # What the plan expected from the same promises and accounts in a normal month (no levers):
        # the basis of each product x stage target.
        pk = logistic(keep_c + self.keep_x_plan)
        plan = (self.ptp_amt * (matured * (pk * 0.975 + (1 - pk) * 0.55 * 0.465) + upcoming * 0.08 * 0.35)
                + ~ptp * self.np_plan * self.bal * 0.07)
        return dict(promise_day=promise_day, due_day=due, matured=matured, upcoming=upcoming,
                    broken=broken_flag, rec=rec, plan=plan)

    def figures(self, o: dict, target_scale: float | None = None, opp_scale: float = 1.0) -> dict:
        """The Command Center figures for one outcome (same formulas as the gold views)."""
        inc = self.dpd > 0
        rec, ptp = o["rec"], self.ptp == 1
        due = ptp & o["matured"] & inc
        broken = (o["broken"] == 1) & inc
        honour = 1 - broken.sum() / max(due.sum(), 1)
        upcoming = ptp & inc & (o["due_day"] > DAYS_ELAPSED) & (o["due_day"] <= DAYS_IN_MONTH)
        collected = rec[inc].sum()
        target = self.targets(o, target_scale)["Monthly_Target"]
        target = target[target.index.get_level_values("DPD_Bucket") != "Current"].sum()
        gap = max(target - collected, 0)
        expected = self.ptp_amt[upcoming].sum() * honour
        week = ptp & inc & (o["due_day"] > DAYS_ELAPSED) & (o["due_day"] <= DAYS_ELAPSED + Q_WINDOW)
        at_risk = week & ((self.prop < Q_BREAK_PROP) | (self.risk >= Q_BREAK_RISK))
        opp = self.opportunity(rec, opp_scale)
        hphb = inc & (self.prop >= Q_HIGH_PROP) & (self.bal >= Q_HIGH_BAL)
        inter = inc & (self.bal > 0) & (self.risk >= HIGH_RISK) & (self.prop >= INTERVENTION_PROP)
        order = np.lexsort((self.v3["Account_ID"].to_numpy(), -np.where(inter, opp, -np.inf)))
        top = np.zeros(self.n, bool); top[order[:PRIORITY_TOP]] = True; top &= inter
        # The way out (gold.qry_cc_action_upside): the at-risk promises saved (the part the outlook
        # doesn't already count) + the high-value and priority accounts worked, recovered at the rate
        # promises are honoured today. Accounts in several queues count once.
        extra = (hphb | top) & ~at_risk
        upside = self.ptp_amt[at_risk].sum() * (1 - honour) + opp[extra].sum() * honour
        return dict(collected=collected, target=target, achievement=collected / target, gap=gap,
                    broken_share=1 - honour, honour=honour, upcoming=self.ptp_amt[upcoming].sum(), expected=expected,
                    coverage=expected / gap if gap else np.inf, outlook=collected + expected,
                    at_risk_amt=self.ptp_amt[at_risk].sum(), hphb_opp=opp[hphb].sum(), priority_opp=opp[top].sum(),
                    inter_opp=opp[inter].sum(), upside=upside, with_action=(collected + expected + upside) / target)

    def opportunity(self, rec, scale: float):
        """Model-style estimate of the extra recovery from working the account, capped at what is left.
        Incremental = paid if worked minus paid if not: larger for a customer likely to pay when worked
        (propensity) who wouldn't pay unprompted (risk)."""
        left = np.maximum(self.bal - rec, 0)
        return np.round(np.minimum(scale * left * self.prop * (0.5 + self.risk) * (0.7 + 0.6 * self.u_opp), left), 2)

    def targets(self, o: dict, scale: float | None) -> pd.DataFrame:
        """October plan: each product x stage at what a normal month would bring from its accounts
        (o["plan"]), with a small product-plan variation, scaled so the plan is a stretch for the month."""
        df = pd.DataFrame({"Product": self.product, "DPD_Bucket": self.bucket, "bal": self.bal, "rec": o["rec"], "plan": o["plan"]})
        g = df.groupby(["Product", "DPD_Bucket"]).agg(Eligible_Balance=("bal", "sum"), rec=("rec", "sum"), plan=("plan", "sum"))
        if not self.pnoise:
            noise = np.exp(np.random.default_rng(SEED + 1).normal(0, 0.04, len(g)))
            self.pnoise = dict(zip(g.index, noise))
        # The plan expects less from 180+ than its promises suggest (late-stage promises rarely hold).
        stage = np.where(g.index.get_level_values("DPD_Bucket") == "180+", 0.82, 1.0)
        plan = g["plan"] * stage * np.array([self.pnoise[i] for i in g.index])
        if scale is None:
            inc = g.index.get_level_values("DPD_Bucket") != "Current"
            scale = g.loc[inc, "rec"].sum() / (CALIBRATION["achievement"] * plan[inc].sum())
        g["Monthly_Target"] = np.round(plan * scale, 2)
        return g

    # ------------------------------------------------------------------------------------------
    def calibrate(self) -> dict:
        c = CALIBRATION
        def keep_for(skew):
            return bisect(lambda k: self.figures(self.outcomes(k, skew))["broken_share"], -4, 6, c["broken_share"], increasing=False)
        skew = bisect(lambda s: self.figures(self.outcomes(keep_for(s), s))["coverage"], 0.4, 4.0, c["gap_coverage"], iters=25)
        keep = keep_for(skew)
        o = self.outcomes(keep, skew)
        f0 = self.figures(o)
        target_scale = f0["collected"] / (c["achievement"] * self.plan_total(o))
        opp_scale = bisect(lambda s: self.figures(o, target_scale, s)["with_action"], 0.01, 1.0, c["outlook_with_action"])
        return dict(keep=keep, skew=skew, target_scale=target_scale, opp_scale=opp_scale, outcome=o)

    def plan_total(self, o):
        g = self.targets(o, 1.0)
        return g.loc[g.index.get_level_values("DPD_Bucket") != "Current", "Monthly_Target"].sum()

    # ------------------------------------------------------------------------------------------
    def build(self, cal: dict) -> dict[str, pd.DataFrame]:
        o, v3, n = cal["outcome"], self.v3, self.n
        day = lambda d: MONTH_START + pd.to_timedelta(d - 1, unit="D")
        ptp = self.ptp == 1
        due_date = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")
        due_date[ptp] = day(o["due_day"][ptp])
        # Last contact: the day the promise was taken, a follow-up after a broken promise, or any
        # October contact day (later days likelier). Never after the snapshot; none if not attempted.
        last = 1 + np.minimum(19, np.floor(20 * self.u_contact_day ** (1 / 1.4))).astype(int)
        last = np.where(ptp, o["promise_day"], last)
        follow = (o["broken"] == 1) & (self.u_follow < 0.55) & (o["due_day"] < DAYS_ELAPSED)
        last = np.where(follow, o["due_day"] + 1 + np.floor(self.u_follow_day * (DAYS_ELAPSED - o["due_day"])).astype(int), last)
        last = np.minimum(last, DAYS_ELAPSED)
        last_date = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")
        att = self.attempts > 0
        last_date[att] = day(last[att])
        rec = o["rec"]
        opp = self.opportunity(rec, cal["opp_scale"])
        fact = pd.DataFrame({
            "Snapshot_Date": AS_OF,
            "Account_ID": v3["Account_ID"], "Customer_Token": v3["Customer_Token"], "Product": self.product,
            "Security_Type": v3["Security_Type"], "Region": self.region, "Preferred_Language": v3["Preferred_Language"],
            "Outstanding_Balance": self.bal, "Balance_Band": self.band, "DPD": self.dpd, "DPD_Bucket": self.bucket,
            "Prior_DPD_Bucket": self.prior, "Annual_Income": v3["Annual_Income"], "Vulnerability_Type": v3["Vulnerability_Type"],
            "Dispute_Flag": self.dispute, "Treatment_Strategy": self.strategy, "Preferred_Channel": self.channel,
            "Collector_ID": self.collector, "Team": self.team, "Attempts_MTD": self.attempts,
            "Voice_Attempts": self.split[:, 0], "WhatsApp_Attempts": self.split[:, 1], "SMS_Attempts": self.split[:, 2],
            "Email_Attempts": self.split[:, 3], "RPC_Flag": self.rpc, "Contacted_Flag": self.contacted,
            "PTP_Flag": self.ptp, "PTP_Amount": self.ptp_amt, "PTP_Due_Date": due_date, "Recovery_MTD": rec,
            "Broken_PTP_Flag": o["broken"], "Cure_Flag": (rec >= CURE_PCT * self.bal).astype(int),
            "Roll_Forward_Flag": self.roll_fwd, "Roll_Back_Flag": self.roll_back, "Cost_MTD": self.cost,
            "Last_Contact_Date": last_date, "Last_Contact_Hour": v3["Last_Contact_Hour"],
            "Payment_Propensity": self.prop, "Nonpayment_Risk": self.risk,
            "Incremental_Recovery_Opportunity": opp, "Primary_Nonpayment_Driver": v3["Primary_Nonpayment_Driver"],
        })[list(v3.columns)]
        g = self.targets(o, cal["target_scale"]).reset_index()
        t = self.sheets["Fact_Targets"][["Product", "DPD_Bucket"]].merge(g, on=["Product", "DPD_Bucket"], how="left")
        targets = pd.DataFrame({
            "Target_Month": MONTH_START, "Product": t["Product"], "DPD_Bucket": t["DPD_Bucket"],
            "Eligible_Balance": np.round(t["Eligible_Balance"], 2), "Monthly_Target": t["Monthly_Target"],
            "Daily_Target": np.round(t["Monthly_Target"] / DAYS_IN_MONTH, 2),
        })
        out = {k: v.copy() for k, v in self.sheets.items()}
        out["Fact_Collections_Snapshot"], out["Fact_Targets"] = fact, targets
        readme = out["README"]
        readme["Detail"] = readme["Detail"].astype(object)
        readme.loc[readme["Item"] == "As-of date", "Detail"] = AS_OF.to_pydatetime()
        readme.loc[readme["Item"] == "Reporting month", "Detail"] = "October 2026"
        readme.loc[len(readme)] = ["v4 data", "Generated by deploy/data/generate_v4_data.py (seed %d) from the v3 pack: the same "
                                   "accounts, with October 2026 month-to-date activity as of 20 October. A realistic month: "
                                   "behind target, promises often broken, recoverable with action." % SEED]
        tests = out["Acceptance_Tests"]
        tests["Expected_Behavior"] = tests["Expected_Behavior"].str.replace("as-of Sep 15 2026", "as-of Oct 20 2026", regex=False)
        # Collectors can't join after the snapshot: a join date in the future moves back a year.
        dim = out["Dim_Collector"]
        late = dim["Join_Date"] > AS_OF
        dim.loc[late, "Join_Date"] = dim.loc[late, "Join_Date"] - pd.DateOffset(years=1)
        return out


def check_rules(fact: pd.DataFrame) -> list[str]:
    """Row-by-row agreement with the workbook rules. Returns the problems (empty = all good)."""
    f, bad = fact, []
    snap = f["Snapshot_Date"]
    matured = (f["PTP_Flag"] == 1) & (f["PTP_Due_Date"] <= snap)
    want = {
        "Broken_PTP_Flag (R05)": (matured & (f["Recovery_MTD"] < BROKEN_PCT * f["PTP_Amount"])).astype(int),
        "Cure_Flag (R06)": (f["Recovery_MTD"] >= CURE_PCT * f["Outstanding_Balance"]).astype(int),
        "Roll_Forward_Flag": (f["DPD_Bucket"].map(ORDER) > f["Prior_DPD_Bucket"].map(ORDER)).astype(int),
        "Roll_Back_Flag": (f["DPD_Bucket"].map(ORDER) < f["Prior_DPD_Bucket"].map(ORDER)).astype(int),
    }
    for name, w in want.items():
        col = name.split(" ")[0]
        if (f[col] != w).any():
            bad.append(f"{name}: {(f[col] != w).sum()} rows disagree")
    checks = {
        "RPC without an attempt (R10)": (f["RPC_Flag"] == 1) & (f["Attempts_MTD"] == 0),
        "PTP without RPC": (f["PTP_Flag"] == 1) & (f["RPC_Flag"] == 0),
        "attempts don't add up": f["Attempts_MTD"] != f[["Voice_Attempts", "WhatsApp_Attempts", "SMS_Attempts", "Email_Attempts"]].sum(1),
        "last contact after snapshot": f["Last_Contact_Date"] > snap,
        "last contact before the month": f["Last_Contact_Date"] < MONTH_START,
        "PTP due date missing or set without a PTP": f["PTP_Due_Date"].notna() != (f["PTP_Flag"] == 1),
        "DPD outside its bucket": ~f.apply(lambda r: DPD_RANGE[r["DPD_Bucket"]][0] <= r["DPD"] <= DPD_RANGE[r["DPD_Bucket"]][1], axis=1),
        "recovery above balance": f["Recovery_MTD"] > f["Outstanding_Balance"],
        "opportunity above what is left": f["Incremental_Recovery_Opportunity"] > f["Outstanding_Balance"] - f["Recovery_MTD"] + 0.01,
    }
    bad += [f"{k}: {int(v.sum())} rows" for k, v in checks.items() if v.any()]
    return bad


def money(v: float) -> str:
    return f"₹{v / 1e6:,.1f}M"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="print the story figures without writing the workbook")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=OUTPUT)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    print(f"Reading {TEMPLATE.name}")
    sheets = pd.read_excel(TEMPLATE, sheet_name=None)
    pack = Pack(sheets, args.seed)
    cal = pack.calibrate()
    f = pack.figures(cal["outcome"], cal["target_scale"], cal["opp_scale"])
    print(f"Calibrated: keep intercept {cal['keep']:.3f}, promise-timing skew {cal['skew']:.3f}, "
          f"target scale {cal['target_scale']:.3f}, opportunity scale {cal['opp_scale']:.4f}")
    print(f"Target {money(f['target'])}, collected {money(f['collected'])} ({f['achievement']:.1%}; "
          f"{DAYS_ELAPSED}/{DAYS_IN_MONTH} days = {DAYS_ELAPSED / DAYS_IN_MONTH:.1%} of the month), gap {money(f['gap'])}")
    print(f"Broken share {f['broken_share']:.1%}; promised rest of month {money(f['upcoming'])}; expected {money(f['expected'])}; "
          f"coverage {f['coverage']:.2f}x; outlook {money(f['outlook'])} ({f['outlook'] / f['target']:.1%})")
    print(f"Chapters 4-5: at-risk promises this week {money(f['at_risk_amt'])}, high-value recoverable {money(f['hphb_opp'])}, "
          f"top {PRIORITY_TOP} priority {money(f['priority_opp'])} of {money(f['inter_opp'])} for all intervention accounts (sum {money(f['at_risk_amt'] + f['hphb_opp'] + f['inter_opp'])} "
          f"vs gap {money(f['gap'])}); upside if acted on {money(f['upside'])} -> {f['with_action']:.1%} of target")
    out = pack.build(cal)
    problems = check_rules(out["Fact_Collections_Snapshot"])
    if problems:
        sys.exit("Rule check failed:\n  " + "\n  ".join(problems))
    print("Rule check: every flag agrees with R04-R07, R10 and the roll definitions")
    if args.check:
        return
    with pd.ExcelWriter(args.out, engine="openpyxl", datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as xw:
        for name in sheets:   # same sheet order as the template
            out[name].to_excel(xw, sheet_name=name, index=False)
    print(f"Wrote {args.out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
