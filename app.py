"""
APP — interface Streamlit du simulateur de bloc opératoire
============================================================

Réutilise tel quel le moteur de bloc_operatoire_sim.py : aucune logique de
simulation n'est réécrite ici, seuls Config et run_scenario sont importés.
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from bloc_operatoire_sim import Config, run_scenario, fmt_clock
from charger_donnees_hug import JOURS_OUVRES, FENETRE

N_REPLICATIONS = 25  # volontairement modeste pour rester réactif dans l'UI

st.set_page_config(page_title="Simulateur de bloc opératoire", layout="wide")

DEFAULTS = dict(
    niveau=3, n_or=4, n_pacu=3, n_circ=4, n_scrub=4, n_anes=4,
    n_elective=20, pct_urgences=15, surgery_mean=75, surgery_std=30,
    turnover_time=30, recovery_mean=90, maintenance=True,
    cout_minute_chf=10.0, cout_fixe_jour_salle=2000.0, majoration_heures_sup=35,
)
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


@st.cache_data
def charger_csv() -> pd.DataFrame:
    return pd.read_csv("donnees_hug_bloc.csv")


def appliquer_preset() -> None:
    """Callback du menu déroulant : remplit les sliders depuis le CSV HUG."""
    nom = st.session_state["preset"]
    if nom == "Aucun (configuration manuelle)":
        return
    row = charger_csv().set_index("specialite").loc[nom]

    par_jour = row["procedures_mensuelles"] / JOURS_OUVRES
    urgences_jour = par_jour * row["pct_urgences"]
    electifs_jour = max(1, round(par_jour - urgences_jour))

    st.session_state["n_or"] = int(row["salles"])
    st.session_state["n_pacu"] = int(row["lits_sspi"])
    st.session_state["n_circ"] = int(row["salles"])
    st.session_state["n_scrub"] = int(row["salles"])
    st.session_state["n_anes"] = int(row["salles"])
    st.session_state["n_elective"] = int(electifs_jour)
    st.session_state["pct_urgences"] = round(float(row["pct_urgences"]) * 100)
    st.session_state["surgery_mean"] = float(row["duree_chir_moy_min"])
    st.session_state["surgery_std"] = float(row["duree_chir_ec_min"])
    st.session_state["recovery_mean"] = float(row["reveil_moy_min"])


def construire_config(n_or, n_pacu, n_circ, n_scrub, n_anes, n_elective,
                       pct_urgences, surgery_mean, surgery_std, turnover_time,
                       recovery_mean, niveau, maintenance, cout_minute_chf,
                       cout_fixe_jour_salle, majoration_heures_sup) -> Config:
    """Traduit les réglages de l'UI en Config — aucune nouvelle logique de simulation."""
    pct = pct_urgences / 100.0
    if pct > 0:
        urgences_jour = n_elective * pct / (1 - pct)
        emergency_interarrival_mean = FENETRE / urgences_jour if urgences_jour > 0.05 else 1e9
    else:
        emergency_interarrival_mean = 1e9
    return Config(
        n_or=n_or, n_pacu=n_pacu, n_circ=n_circ, n_scrub=n_scrub, n_anes=n_anes,
        n_elective=n_elective, emergency_interarrival_mean=emergency_interarrival_mean,
        arrival_window=FENETRE,
        surgery_mean=surgery_mean, surgery_std=surgery_std,
        turnover_time=turnover_time, recovery_mean=recovery_mean,
        recovery_std=recovery_mean * 0.35,
        use_sspi=niveau >= 2, use_personnel=niveau >= 3, use_maintenance=maintenance,
        maint_proba=0.3 if maintenance else 0.0, maint_dur=180.0,
        cout_minute_chf=cout_minute_chf, cout_fixe_jour_salle=cout_fixe_jour_salle,
        majoration_heures_sup=majoration_heures_sup / 100.0,
        n_replications=N_REPLICATIONS,
    )


def generer_lecture(r: dict) -> str:
    candidats = [
        ("le blocage SSPI (manque de lits de réveil)", r["blocage_sspi_min"], r["cout_gaspillage_chf"]),
        ("le manque de personnel", r["salle_min_perdues_personnel"], r["cout_gaspillage_chf"]),
        ("les heures supplémentaires", r["heures_sup_min"], r["cout_heures_sup_chf"]),
    ]
    nom, minutes, cout = max(candidats, key=lambda c: c[1])
    return (
        f"Le dernier patient sort à {fmt_clock(r['makespan_min'])} pour "
        f"{r['cas_total']:.0f} cas traités ({r['occupation_salle_%']:.0f}% d'occupation des salles). "
        f"Le goulot dominant est **{nom}** ({minutes:.0f} min), associé à environ "
        f"{cout:,.0f} CHF sur un coût total de {r['cout_total_chf']:,.0f} CHF/jour. "
        f"Comparez avec les options « +1 salle » et « +2 lits SSPI » ci-dessous pour juger "
        f"si l'investissement correspondant serait rentable."
    )


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.title("Configuration")

df_specs = charger_csv()
st.sidebar.selectbox(
    "Préréglage par spécialité",
    ["Aucun (configuration manuelle)"] + list(df_specs["specialite"]),
    key="preset", on_change=appliquer_preset,
)

st.sidebar.subheader("Niveau de complexité")
niveau = st.sidebar.slider("1 = salle seule … 4 = + maintenance", 1, 4, key="niveau")

st.sidebar.subheader("Ressources")
n_or = st.sidebar.slider("Nombre de salles", 1, 12, key="n_or")
n_pacu = st.sidebar.slider("Lits SSPI (réveil)", 1, 12, key="n_pacu")

st.sidebar.subheader("Effectifs présents")
n_circ = st.sidebar.slider("Circulants", 0, 12, key="n_circ")
n_scrub = st.sidebar.slider("Instrumentistes", 0, 12, key="n_scrub")
n_anes = st.sidebar.slider("Anesthésie", 0, 12, key="n_anes")

st.sidebar.subheader("Demande")
n_elective = st.sidebar.slider("Cas programmés (électifs)", 1, 60, key="n_elective")
pct_urgences = st.sidebar.slider("Part d'urgences (%)", 0, 60, key="pct_urgences")

st.sidebar.subheader("Durées (minutes)")
surgery_mean = st.sidebar.slider("Durée opératoire moyenne", 15, 240, key="surgery_mean")
surgery_std = st.sidebar.slider("Écart-type durée opératoire", 5, 100, key="surgery_std")
turnover_time = st.sidebar.slider("Turnover (nettoyage)", 10, 60, key="turnover_time")
recovery_mean = st.sidebar.slider("Durée de réveil moyenne", 15, 240, key="recovery_mean")

st.sidebar.subheader("Maintenance")
maintenance = st.sidebar.toggle("Maintenance & QA des équipements", key="maintenance")

st.sidebar.subheader("Coûts (CHF)")
cout_minute_chf = st.sidebar.slider(
    "Coût variable à la minute", 0.0, 30.0, step=0.5, key="cout_minute_chf")
cout_fixe_jour_salle = st.sidebar.slider(
    "Coût fixe par salle et par jour", 0.0, 5000.0, step=100.0, key="cout_fixe_jour_salle")
majoration_heures_sup = st.sidebar.slider(
    "Majoration heures sup (%)", 0, 100, key="majoration_heures_sup")
st.sidebar.caption(
    "**Variable** : personnel + consommables, payé à la minute de salle occupée. "
    "**Fixe** : amortissement équipement + immobilier, payé par salle et par jour "
    "qu'elle tourne ou non. Séparer les deux évite de compter le capital deux fois "
    "dans le tarif à la minute."
)

# ---------------------------------------------------------------------------
# ZONE PRINCIPALE
# ---------------------------------------------------------------------------
st.title("Simulateur de bloc opératoire")
st.caption(f"{N_REPLICATIONS} répétitions par scénario · ouverture 08:00 · fermeture prévue 16:00.")

cfg = construire_config(n_or, n_pacu, n_circ, n_scrub, n_anes, n_elective,
                         pct_urgences, surgery_mean, surgery_std, turnover_time,
                         recovery_mean, niveau, maintenance, cout_minute_chf,
                         cout_fixe_jour_salle, majoration_heures_sup)

with st.spinner("Simulation en cours..."):
    r = run_scenario(cfg)

st.subheader("Temporel")
c1, c2, c3 = st.columns(3)
c1.metric("Heure de fin", fmt_clock(r["makespan_min"]))
c2.metric("Occupation des salles", f"{r['occupation_salle_%']:.0f}%")
c3.metric("Cas traités", f"{r['cas_total']:.0f}")

st.subheader("Goulots")
c4, c5, c6 = st.columns(3)
c4.metric("Blocage SSPI", f"{r['blocage_sspi_min']:.0f} min")
c5.metric("Salle-min perdues (personnel)", f"{r['salle_min_perdues_personnel']:.0f} min")
c6.metric("Heures supplémentaires", f"{r['heures_sup_min']:.0f} min")

st.subheader("Coûts (CHF)")
c7, c8, c9 = st.columns(3)
c7.metric("Coût total", f"{r['cout_total_chf']:,.0f} CHF")
c8.metric("dont heures sup", f"{r['cout_heures_sup_chf']:,.0f} CHF")
c9.metric("Coût par cas", f"{r['cout_par_cas_chf']:,.0f} CHF")

st.subheader("Comparaison avec deux investissements")
with st.spinner("Simulation des scénarios comparatifs..."):
    cfg_salle = construire_config(n_or + 1, n_pacu, n_circ, n_scrub, n_anes, n_elective,
                                   pct_urgences, surgery_mean, surgery_std, turnover_time,
                                   recovery_mean, niveau, maintenance, cout_minute_chf,
                                   cout_fixe_jour_salle, majoration_heures_sup)
    cfg_sspi = construire_config(n_or, n_pacu + 2, n_circ, n_scrub, n_anes, n_elective,
                                  pct_urgences, surgery_mean, surgery_std, turnover_time,
                                  recovery_mean, niveau, maintenance, cout_minute_chf,
                                  cout_fixe_jour_salle, majoration_heures_sup)
    r_salle = run_scenario(cfg_salle)
    r_sspi = run_scenario(cfg_sspi)

noms = ["Configuration actuelle", "+1 salle", "+2 lits SSPI"]
fins = [r["makespan_min"] / 60 + 8, r_salle["makespan_min"] / 60 + 8, r_sspi["makespan_min"] / 60 + 8]
couts = [r["cout_total_chf"], r_salle["cout_total_chf"], r_sspi["cout_total_chf"]]
colors = ["#2980b9", "#e67e22", "#27ae60"]

fig, axes = plt.subplots(1, 2, figsize=(11, 4))
axes[0].bar(noms, fins, color=colors)
axes[0].axhline(16, ls="--", color="grey", lw=1)
axes[0].set_title("Heure de fin")
axes[0].set_ylabel("heure")

axes[1].bar(noms, couts, color=colors)
axes[1].set_title("Coût total (CHF/jour)")
axes[1].set_ylabel("CHF")

for ax in axes:
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)

fig.tight_layout()
st.pyplot(fig)

st.subheader("Lecture")
st.markdown(generer_lecture(r))
