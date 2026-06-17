"""
DÉMO — Main d'oeuvre du bloc opératoire
=======================================

Deux questions traitées :
  1) Dimensionnement : combien d'EPT recruter (méthode AORN + facteur de couverture) ?
  2) Absentéisme : que se passe-t-il quand des soignants manquent ?

S'appuie sur le moteur de bloc_operatoire_sim.py (contrainte d'équipe ajoutée :
une salle ne démarre un cas que si circulant + instrumentiste + anesthésie
sont disponibles).
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bloc_operatoire_sim import Config, run_scenario, effectifs_a_recruter, fmt_clock


# Bloc représentatif : 6 salles, charge soutenue (cas de 100 min en moyenne).
BASE = dict(n_or=6, n_pacu=6, n_elective=20, emergency_interarrival_mean=120,
            surgery_mean=100, surgery_std=40, recovery_mean=90, recovery_std=30,
            turnover_time=30, morning_qa_time=15, n_replications=40)


def partie_1_dimensionnement():
    print("\n" + "=" * 78)
    print(" 1) DIMENSIONNEMENT — EPT à recruter (plateau adulte ~20 salles de jour)")
    print("=" * 78)
    print(f"{'Hypothèse':<42}{'EPT au sol':>11}{'À recruter':>12}")
    print("-" * 78)
    scenarios = [
        ("2 pers./salle (circ+instr.), couv. US 1.14", 2.0, 1.14),
        ("2 pers./salle, couverture Suisse 1.27", 2.0, 1.27),
        ("3 pers./salle (+ anesthésie), couv. 1.27", 3.0, 1.27),
        ("3 pers./salle, absentéisme élevé 1.35", 3.0, 1.35),
    ]
    for libelle, pers, couv in scenarios:
        r = effectifs_a_recruter(salles_jour=20, personnes_par_salle=pers,
                                 heures_jour=9, jours_semaine=5,
                                 heures_ept_semaine=42, facteur_couverture=couv)
        print(f"{libelle:<42}{r['ept_base_au_sol']:>11.1f}{r['ept_a_recruter']:>12.1f}")
    print("-" * 78)
    print("  Lecture : le facteur de couverture (vacances+maladie+formation) ajoute")
    print("  ~25-35% d'EPT. C'est la marge qui évite de fermer une salle en cas d'absence.\n")


def partie_2_absenteisme():
    print("=" * 78)
    print(" 2) ABSENTÉISME — effet du manque de circulants (bloc de 6 salles)")
    print("=" * 78)
    print(f"{'Effectif circulants':<24}{'Pic salles':>11}{'Salle-min':>11}{'H.sup':>8}{'Fin':>8}")
    print(f"{'présents':<24}{'parallèle':>11}{'perdues':>11}{'(min)':>8}{'':>8}")
    print("-" * 78)

    absences = [0, 1, 2, 3]
    pics, perdues, makespans = [], [], []
    for a in absences:
        cfg = Config(**BASE, n_circ=6 - a)
        r = run_scenario(cfg)
        pics.append(r["pic_equipes"])
        perdues.append(r["salle_min_perdues_personnel"])
        makespans.append(r["makespan_min"])
        libelle = f"{6 - a} présents (-{a})" if a else "6 présents (complet)"
        print(f"{libelle:<24}{r['pic_equipes']:>11.1f}{r['salle_min_perdues_personnel']:>11.0f}"
              f"{r['heures_sup_min']:>8.0f}{fmt_clock(r['makespan_min']):>8}")
    print("-" * 78)
    print("  Chaque circulant absent = une salle de moins qui peut tourner en parallèle,")
    print("  donc des cas repoussés, des heures sup et une journée qui s'étire.\n")
    return absences, pics, perdues, makespans


def graphique(absences, pics, perdues, makespans):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    x = [f"-{a}" if a else "complet" for a in absences]
    colors = ["#27ae60", "#f1c40f", "#e67e22", "#c0392b"]

    axes[0].bar(x, pics, color=colors)
    axes[0].set_title("Salles tournant\nen parallèle (pic)")
    axes[0].set_ylabel("salles")

    axes[1].bar(x, perdues, color=colors)
    axes[1].set_title("Salle-minutes perdues\nfaute de personnel")
    axes[1].set_ylabel("minutes")

    axes[2].bar(x, [m / 60 + 8 for m in makespans], color=colors)
    axes[2].set_title("Heure de fin\n(dernier patient)")
    axes[2].set_ylabel("heure")
    axes[2].set_ylim(16, 26)

    for ax in axes:
        ax.grid(axis="y", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("circulants absents")

    fig.suptitle("Impact de l'absentéisme sur le bloc opératoire", fontweight="bold")
    fig.tight_layout()
    fig.savefig("personnel_resultats.png", dpi=130, bbox_inches="tight")
    print("Graphique enregistré : personnel_resultats.png")


if __name__ == "__main__":
    partie_1_dimensionnement()
    data = partie_2_absenteisme()
    graphique(*data)
