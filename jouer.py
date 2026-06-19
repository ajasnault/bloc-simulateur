"""
JOUER — pose les questions de dimensionnement une par une, lance la simulation
avec les réponses, et affiche les KPIs en clair. Relançable à volonté pour
tester différentes configurations.
"""
from __future__ import annotations
from bloc_operatoire_sim import Config, run_scenario, fmt_clock

NIVEAUX = {
    1: "salle seule (le strict minimum)",
    2: "+ SSPI / réveil (et le blocage d'aval)",
    3: "+ personnel (équipe requise pour ouvrir une salle)",
    4: "+ maintenance & QA des équipements",
}


def ask_int(label: str, default: int) -> int:
    while True:
        raw = input(f"{label} [{default}] : ").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            print("  -> entrez un nombre entier, réessayez.")


def ask_niveau() -> int:
    print("\nNiveaux de complexité disponibles :")
    for n, desc in NIVEAUX.items():
        print(f"  {n} : {desc}")
    while True:
        raw = input("Niveau de complexité (1-4) [3] : ").strip()
        if raw == "":
            return 3
        if raw in ("1", "2", "3", "4"):
            return int(raw)
        print("  -> entrez un chiffre entre 1 et 4.")


def collecter_config() -> Config:
    niveau = ask_niveau()
    n_or = ask_int("\nNombre de salles d'opération", 4)
    n_pacu = ask_int("Nombre de lits SSPI (réveil)", 3)
    n_elective = ask_int("Nombre de cas programmés (électifs)", 20)

    n_circ = n_scrub = n_anes = None
    if niveau >= 3:
        print(f"\nEffectifs présents aujourd'hui (laisser vide = équipe complète, soit {n_or} par poste) :")
        n_circ = ask_int("  Infirmiers circulants", n_or)
        n_scrub = ask_int("  Instrumentistes", n_or)
        n_anes = ask_int("  Personnel d'anesthésie", n_or)

    return Config(niveau=niveau, n_or=n_or, n_pacu=n_pacu, n_elective=n_elective,
                  n_circ=n_circ, n_scrub=n_scrub, n_anes=n_anes)


def afficher_resultats(cfg: Config, r: dict) -> None:
    print("\n" + "=" * 60)
    print(" RÉSULTATS DE LA SIMULATION")
    print("=" * 60)
    print(f"Niveau de complexité          : {cfg.niveau} ({NIVEAUX[cfg.niveau]})")
    print(f"Salles d'opération             : {cfg.n_or}")
    print(f"Lits SSPI (réveil)              : {cfg.n_pacu}")
    print(f"Cas programmés (électifs)      : {cfg.n_elective}")
    if cfg.niveau >= 3:
        print(f"Effectifs (circ/instr./anes.)  : {cfg.n_circ}/{cfg.n_scrub}/{cfg.n_anes}")
    print("-" * 60)
    print(f"Cas traités (total)            : {r['cas_total']:.0f}")
    print(f"Occupation des salles           : {r['occupation_salle_%']:.0f}%")
    print(f"Blocage SSPI                    : {r['blocage_sspi_min']:.0f} min")
    if cfg.niveau >= 3:
        print(f"Salle-minutes perdues (perso.) : {r['salle_min_perdues_personnel']:.0f} min")
        print(f"Pic de salles en parallèle      : {r['pic_equipes']:.1f}")
    if cfg.niveau >= 4:
        print(f"Downtime QA + maintenance       : {r['downtime_qa_min'] + r['downtime_maint_min']:.0f} min")
    print(f"Heures supplémentaires          : {r['heures_sup_min']:.0f} min")
    print(f"Heure de fin (dernier patient)  : {fmt_clock(r['makespan_min'])}")
    print("-" * 60)
    print(f"Coût total                      : {r['cout_total_chf']:,.0f} CHF")
    print(f"  dont heures supplémentaires    : {r['cout_heures_sup_chf']:,.0f} CHF")
    print(f"  dont gaspillage (blocage+perso) : {r['cout_gaspillage_chf']:,.0f} CHF")
    print(f"  coût par cas                    : {r['cout_par_cas_chf']:,.0f} CHF")
    print("=" * 60)


def main() -> None:
    print("Simulateur de bloc opératoire — testez vos propres configurations.")
    while True:
        cfg = collecter_config()
        print("\nSimulation en cours (40 répétitions)...")
        r = run_scenario(cfg)
        afficher_resultats(cfg, r)

        again = input("\nTester une autre configuration ? (o/n) [o] : ").strip().lower()
        if again in ("n", "non"):
            break
    print("\nÀ bientôt !")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nInterrompu.")
