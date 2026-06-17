"""
DÉMO — Empiler la complexité, niveau par niveau
===============================================

On lance EXACTEMENT le même scénario (mêmes salles, même charge, mêmes durées)
en activant une couche de plus à chaque fois. On voit ainsi ce que chaque
brique ajoute à la difficulté de planification.

    Niveau 1 : salle seule
    Niveau 2 : + SSPI (réveil) et blocage d'aval
    Niveau 3 : + personnel (ici on simule -2 instrumentistes pour que ça morde)
    Niveau 4 : + maintenance & QA des équipements

Astuce : la contrainte "personnel" ne change rien tant que l'effectif est
complet. Pour la rendre visible au niveau 3+, on retire 2 instrumentistes.
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bloc_operatoire_sim import Config, run_scenario, fmt_clock

# Scénario commun à tous les niveaux
COMMUN = dict(n_or=5, n_pacu=4, n_elective=18,
              surgery_mean=90, surgery_std=35, recovery_mean=90, recovery_std=30,
              turnover_time=30, morning_qa_time=15, maint_proba=0.3, maint_dur=180,
              n_replications=40)


def main():
    niveaux = {
        "Niveau 1\nsalle seule": Config(niveau=1, **COMMUN),
        "Niveau 2\n+ SSPI": Config(niveau=2, **COMMUN),
        "Niveau 3\n+ personnel (-2)": Config(niveau=3, n_scrub=3, **COMMUN),
        "Niveau 4\n+ maintenance": Config(niveau=4, n_scrub=3, **COMMUN),
    }
    res = {nom: run_scenario(cfg) for nom, cfg in niveaux.items()}

    print("\n" + "=" * 84)
    print(" EMPILEMENT DES NIVEAUX DE COMPLEXITÉ — même scénario, une couche de plus à chaque fois")
    print("=" * 84)
    print(f"{'Niveau':<22}{'Occup.':>8}{'Blocage':>9}{'Perte':>8}{'Down':>7}{'H.sup':>8}{'Fin':>8}")
    print(f"{'':<22}{'salle':>8}{'SSPI':>9}{'perso':>8}{'time':>7}{'(min)':>8}{'':>8}")
    print("-" * 84)
    for nom, r in res.items():
        label = nom.replace("\n", " ")
        print(f"{label:<22}{r['occupation_salle_%']:>7.0f}%{r['blocage_sspi_min']:>9.0f}"
              f"{r['salle_min_perdues_personnel']:>8.0f}"
              f"{r['downtime_qa_min'] + r['downtime_maint_min']:>7.0f}"
              f"{r['heures_sup_min']:>8.0f}{fmt_clock(r['makespan_min']):>8}")
    print("=" * 84)
    print("  Chaque couche rapproche le modèle de la réalité — et repousse l'heure de fin.\n")

    # --- graphique : heure de fin qui se dégrade en empilant les couches ---
    noms = list(niveaux.keys())
    fins = [res[n]["makespan_min"] / 60 + 8 for n in noms]
    colors = ["#27ae60", "#2980b9", "#e67e22", "#c0392b"]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    bars = ax.bar(noms, fins, color=colors)
    ax.axhline(16, ls="--", color="grey", lw=1)
    ax.text(3.4, 16.1, "fin prévue 16:00", color="grey", ha="right", fontsize=9)
    ax.set_ylabel("heure de fin du dernier patient")
    ax.set_ylim(14, max(fins) + 1)
    ax.set_title("Empiler la complexité = se rapprocher de la réalité du bloc",
                 fontweight="bold")
    for b, f in zip(bars, fins):
        h, m = divmod(int(round((f - 8) * 60)) + 8 * 60, 60)
        ax.text(b.get_x() + b.get_width() / 2, f + 0.05, f"{h:02d}:{m:02d}",
                ha="center", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("niveaux_resultats.png", dpi=130, bbox_inches="tight")
    print("Graphique enregistré : niveaux_resultats.png")


if __name__ == "__main__":
    main()
