"""
DÉMO — Module de coûts (CHF)
============================

Traduit en francs suisses l'arbitrage déjà visible dans les KPIs opérationnels :
faut-il ajouter une salle, des lits de SSPI, ou renforcer une équipe, plutôt
que de laisser filer les heures supplémentaires ?

Scénario de référence "sous tension" (4 salles / 3 SSPI), avec en plus un
déficit volontaire d'une équipe complète (-1 circulant/instrumentiste/anesthésie)
pour que les TROIS leviers comparés soient chacun réellement contraignants.

cout_fixe_jour_salle est fixé à 2000 CHF/jour/salle pour ce scénario (hypothèse
d'amortissement équipement + locaux) afin que "+1 salle" représente un vrai
investissement, et pas une capacité gratuite.
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bloc_operatoire_sim import Config, run_scenario, fmt_clock

BASE = dict(n_elective=20, surgery_mean=90, surgery_std=35,
            recovery_mean=90, recovery_std=30, turnover_time=30,
            n_replications=40, cout_fixe_jour_salle=2000.0)

OPTIONS = {
    "Référence (sous tension)": Config(n_or=4, n_pacu=3, n_circ=3, n_scrub=3, n_anes=3, **BASE),
    "+1 salle":                 Config(n_or=5, n_pacu=3, n_circ=3, n_scrub=3, n_anes=3, **BASE),
    "+2 lits SSPI":              Config(n_or=4, n_pacu=5, n_circ=3, n_scrub=3, n_anes=3, **BASE),
    "+1 équipe complète":        Config(n_or=4, n_pacu=3, n_circ=4, n_scrub=4, n_anes=4, **BASE),
}


def main():
    res = {nom: run_scenario(cfg) for nom, cfg in OPTIONS.items()}

    print("\n" + "=" * 92)
    print(" MODULE DE COÛTS — arbitrer salle / SSPI / personnel en francs suisses")
    print(" (moyennes sur 40 répétitions ; cout_minute_chf=15, majoration H.sup=35%,")
    print("  cout_fixe_jour_salle=2000 CHF/jour/salle)")
    print("=" * 92)
    print(f"{'Option':<28}{'H.sup':>8}{'Coût total':>13}{'Coût H.sup':>13}"
          f"{'Gaspillage':>13}{'Coût/cas':>11}")
    print(f"{'':<28}{'(min)':>8}{'(CHF)':>13}{'(CHF)':>13}{'(CHF)':>13}{'(CHF)':>11}")
    print("-" * 92)
    for nom, r in res.items():
        print(f"{nom:<28}{r['heures_sup_min']:>8.0f}{r['cout_total_chf']:>13,.0f}"
              f"{r['cout_heures_sup_chf']:>13,.0f}{r['cout_gaspillage_chf']:>13,.0f}"
              f"{r['cout_par_cas_chf']:>11,.0f}")
    print("=" * 92)

    # ---- synthèse : option la moins chère ----
    meilleur_nom = min(res, key=lambda n: res[n]["cout_total_chf"])
    ref, meilleur = res["Référence (sous tension)"], res[meilleur_nom]
    economie = ref["cout_total_chf"] - meilleur["cout_total_chf"]
    print(f"\nSYNTHÈSE : l'option la moins chère est \"{meilleur_nom}\""
          f" ({meilleur['cout_total_chf']:,.0f} CHF/jour),")
    if meilleur_nom == "Référence (sous tension)":
        print("  -> aucune des options testées ne réduit le coût total : le statu quo l'emporte.\n")
    else:
        print(f"  soit {economie:,.0f} CHF/jour de moins que la référence, principalement"
              f" en évitant {ref['heures_sup_min'] - meilleur['heures_sup_min']:.0f} min"
              f" d'heures supplémentaires.\n")

    # ---- graphique ----
    noms = list(OPTIONS.keys())
    couts = [res[n]["cout_total_chf"] for n in noms]
    colors = ["#c0392b", "#e67e22", "#2980b9", "#27ae60"]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    bars = ax.bar(noms, couts, color=colors)
    ax.set_ylabel("coût total (CHF/jour)")
    ax.set_title("Arbitrage salle / SSPI / personnel — coût total en francs",
                 fontweight="bold")
    for b, c in zip(bars, couts):
        ax.text(b.get_x() + b.get_width() / 2, c, f"{c:,.0f}", ha="center",
                va="bottom", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("couts_resultats.png", dpi=130, bbox_inches="tight")
    print("Graphique enregistré : couts_resultats.png")


if __name__ == "__main__":
    main()
