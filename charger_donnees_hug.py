"""
Charge le jeu de données HUG (donnees_hug_bloc.csv) et lance la simulation
de bloc opératoire pour CHAQUE spécialité, puis affiche un tableau comparatif.

Les volumes mensuels sont convertis en charge journalière sur une base de
21 jours ouvrés ; la part d'urgences devient un flux poissonien, le reste
des cas devient le programme opératoire du jour.

Réutilise le moteur écrit dans bloc_operatoire_sim.py.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from bloc_operatoire_sim import Config, run_scenario, fmt_clock

JOURS_OUVRES = 21          # jours ouvrés par mois (pour le programme électif)
FENETRE = 480.0            # fenêtre d'arrivée des urgences (8h)


def config_depuis_ligne(row) -> Config:
    """Transforme une ligne du CSV (données HUG) en un scénario simulable."""
    par_jour = row["procedures_mensuelles"] / JOURS_OUVRES
    urgences_jour = par_jour * row["pct_urgences"]
    electifs_jour = max(1, round(par_jour - urgences_jour))

    interarrivee = FENETRE / urgences_jour if urgences_jour > 0.05 else 1e9

    return Config(
        n_or=int(row["salles"]),
        n_pacu=int(row["lits_sspi"]),
        n_elective=int(electifs_jour),
        emergency_interarrival_mean=float(interarrivee),
        arrival_window=FENETRE,
        surgery_mean=float(row["duree_chir_moy_min"]),
        surgery_std=float(row["duree_chir_ec_min"]),
        recovery_mean=float(row["reveil_moy_min"]),
        recovery_std=float(row["reveil_moy_min"]) * 0.35,
        n_replications=30,
    )


def main():
    df = pd.read_csv("donnees_hug_bloc.csv")

    print("\n" + "=" * 92)
    print(" BLOC OPÉRATOIRE HUG — simulation par spécialité (données calibrées sur les agrégats publics)")
    print(" Programme 08:00–16:00, moyennes sur 30 répétitions par spécialité")
    print("=" * 92)
    print(f"{'Spécialité':<26}{'Sal':>4}{'SSPI':>5}{'Cas/j':>7}{'Occup':>8}"
          f"{'Blocage':>9}{'H.sup':>7}{'Att.':>7}{'Fin':>8}")
    print(f"{'':<26}{'':>4}{'':>5}{'(él+urg)':>7}{'salle':>8}{'(min)':>9}{'(min)':>7}{'(min)':>7}{'':>8}")
    print("-" * 92)

    totaux = {"salles": 0, "cas_jour": 0.0}
    for _, row in df.iterrows():
        cfg = config_depuis_ligne(row)
        res = run_scenario(cfg)
        cas_jour = res["cas_total"]
        totaux["salles"] += cfg.n_or
        totaux["cas_jour"] += cas_jour
        print(f"{row['specialite']:<26}{cfg.n_or:>4}{cfg.n_pacu:>5}{cas_jour:>7.0f}"
              f"{res['occupation_salle_%']:>7.0f}%"
              f"{res['blocage_sspi_min']:>9.0f}"
              f"{res['heures_sup_min']:>7.0f}"
              f"{res['attente_moy_salle_min']:>6.0f}m"
              f"{fmt_clock(res['makespan_min']):>8}")

    print("-" * 92)
    print(f"{'TOTAL plateau adulte':<26}{totaux['salles']:>4}{'':>5}{totaux['cas_jour']:>7.0f}")
    print("=" * 92)
    print(f"\n  Rappel des agrégats réels HUG : 24 salles opératoires (plateau adulte),")
    print(f"  ~30 000 interventions/an (adulte + pédiatrie), 35% d'urgences.")
    print(f"  Total simulé ici : {totaux['salles']} salles, "
          f"~{totaux['cas_jour'] * JOURS_OUVRES * 12:,.0f} interventions/an sur le périmètre modélisé.\n")


if __name__ == "__main__":
    main()
