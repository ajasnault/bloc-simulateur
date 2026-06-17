"""
Simulation à événements discrets d'un BLOC OPÉRATOIRE
=====================================================

Prototype pédagogique reproduisant la logique d'un outil type FlexSim, mais
écrit "à la main" pour rester totalement transparent.

Le moteur n'utilise que la bibliothèque standard (heapq = file d'événements).
numpy sert uniquement aux tirages aléatoires, matplotlib au graphique final.

Le modèle illustre volontairement un phénomène contre-intuitif et central en
planification de bloc : le GOULOT D'AVAL. Quand la salle de réveil (SSPI / PACU)
manque de lits, un patient opéré ne peut pas quitter la salle d'opération ; la
salle reste donc "bloquée" (ni productive, ni disponible). Résultat : ajouter
des lits de SSPI peut augmenter le débit du bloc PLUS que d'ajouter une salle.

Flux d'un cas (patient) :
    arrivée -> file d'attente salle -> [induction + chirurgie] dans une salle
            -> besoin d'un lit de SSPI
                 - lit dispo : le patient part en SSPI, la salle est nettoyée (turnover)
                 - pas de lit : le patient RESTE dans la salle (blocage) jusqu'à libération
            -> réveil en SSPI -> sortie

Auteur : prototype généré pour préparation d'entretien (planificateur de bloc).

-----------------------------------------------------------------------------
NIVEAUX DE COMPLEXITÉ  (commence simple, empile ensuite)
-----------------------------------------------------------------------------
    Config(niveau=1)  ->  salle seule (le strict minimum)
    Config(niveau=2)  ->  + SSPI / réveil + blocage d'aval
    Config(niveau=3)  ->  + personnel (équipe requise pour ouvrir une salle)
    Config(niveau=4)  ->  + maintenance & QA des équipements

Chaque couche est isolée derrière un drapeau (use_sspi, use_personnel,
use_maintenance) et balisée dans le code par un commentaire "NIVEAU n".

RECETTE pour ajouter un nouveau bloc (ex. un futur "NIVEAU 5 : chirurgien") :
    1. Ajouter un drapeau dans Config (ex. use_chirurgien) + ses paramètres.
    2. Déclarer la ressource dans ORSimulation.__init__ (ex. un pool par spécialité).
    3. L'exiger dans _can_start() (la salle ne part que si le chirurgien est libre).
    4. La saisir dans try_start_or() et la libérer dans on_surgery_end().
    5. Exposer un KPI dans _compute_metrics() et l'agréger dans run_scenario().
C'est exactement le chemin suivi par la couche "personnel" : copie-la comme patron.
"""

from __future__ import annotations
import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field
import numpy as np


# ---------------------------------------------------------------------------
# 1. PARAMÉTRAGE  (toutes les durées sont en MINUTES)
# ---------------------------------------------------------------------------
@dataclass
class Config:
    # --- Ressources (variables de capacité) ---
    n_or: int = 4               # nombre de salles d'opération
    n_pacu: int = 3             # nombre de lits en SSPI (salle de réveil)

    # --- Demande (variables d'entrée subies) ---
    n_elective: int = 20        # cas programmés, tous "prêts" à l'ouverture (08:00)
    emergency_interarrival_mean: float = 100.0   # urgences : loi de Poisson
    arrival_window: float = 480.0               # urgences possibles sur la journée (8h)

    # --- Durées de process (lois log-normales, typiques en chirurgie) ---
    induction_time: float = 15.0          # induction anesthésique (fixe, simplifié)
    surgery_mean: float = 75.0            # durée opératoire moyenne
    surgery_std: float = 30.0
    # Turnover = nettoyage + set-up complet (sortie patient -> entrée suivant).
    # Repère littérature : benchmark 30 min ; centre tertiaire ~35 min ;
    # ambulatoire <20 min ; moyenne observée ~39 min (cf. recherche web).
    turnover_time: float = 30.0
    recovery_mean: float = 90.0           # durée de réveil en SSPI
    recovery_std: float = 30.0

    # --- Maintenance & calibration des équipements (variables à explorer) ---
    # QA matinale : mise en route robot / contrôle imagerie / check anesthésie.
    # Toutes les salles sont indisponibles tant que ce contrôle n'est pas fait.
    morning_qa_time: float = 15.0
    # Maintenance préventive : chaque jour, probabilité qu'UNE salle soit retirée
    # du circuit pendant 'maint_dur' minutes (robot da Vinci ~99% uptime, donc
    # quelques % de jours concernés ; imagerie hybride à calibrer périodiquement).
    maint_proba: float = 0.0
    maint_dur: float = 180.0

    # --- Horaires ---
    scheduled_close: float = 480.0        # fin de vacation = 16:00 (au-delà = heures sup)

    # --- Main d'oeuvre (effectifs PRÉSENTS aujourd'hui) ---
    # Une salle ne démarre un cas que si 1 circulant + 1 instrumentiste +
    # 1 anesthésie sont libres. Baisser ces nombres = simuler l'absentéisme
    # (maladie, formation, vacances) -> des salles restent fermées.
    # Par défaut : effectif complet (= une équipe par salle).
    n_circ: int = None          # infirmiers circulants présents
    n_scrub: int = None         # instrumentistes présents
    n_anes: int = None          # personnel d'anesthésie présent

    # --- Expérimentation ---
    n_replications: int = 40              # répétitions (modèle stochastique)
    base_seed: int = 20240601

    # =====================================================================
    # NIVEAUX DE COMPLEXITÉ  (le coeur de cette version : on empile les couches)
    # ---------------------------------------------------------------------
    #   niveau 1 : salle seule (le strict minimum pour apprendre)
    #   niveau 2 : + SSPI / réveil (et le blocage d'aval)
    #   niveau 3 : + personnel (équipe requise pour ouvrir une salle)
    #   niveau 4 : + maintenance & QA des équipements
    # Mets 'niveau' pour activer d'un coup, ou pilote chaque drapeau à la main.
    # =====================================================================
    niveau: int = None
    use_sspi: bool = True
    use_personnel: bool = True
    use_maintenance: bool = True

    def __post_init__(self):
        # Si un niveau est demandé, il fixe les drapeaux (sinon, drapeaux manuels).
        if self.niveau is not None:
            self.use_sspi = self.niveau >= 2
            self.use_personnel = self.niveau >= 3
            self.use_maintenance = self.niveau >= 4
        # Effectif complet par défaut : une équipe complète par salle.
        if self.n_circ is None:
            self.n_circ = self.n_or
        if self.n_scrub is None:
            self.n_scrub = self.n_or
        if self.n_anes is None:
            self.n_anes = self.n_or


def draw_lognormal(rng: np.random.Generator, mean: float, std: float) -> float:
    """Tire une durée > 0 d'une loi log-normale de moyenne et écart-type donnés."""
    if mean <= 0:
        return 0.0
    sigma2 = np.log(1.0 + (std / mean) ** 2)
    mu = np.log(mean) - sigma2 / 2.0
    return float(rng.lognormal(mu, np.sqrt(sigma2)))


# ---------------------------------------------------------------------------
# 2. ENTITÉ : un cas chirurgical (le "flowitem")
# ---------------------------------------------------------------------------
@dataclass
class Case:
    cid: int
    kind: str                       # 'elective' ou 'emergency'
    arrival: float
    surgery_dur: float
    recovery_dur: float
    # horodatages remplis pendant la simulation :
    seize_start: float = None       # début d'occupation de la salle
    surgery_end: float = None       # fin de chirurgie
    block_start: float = None       # début d'attente d'un lit SSPI (dans la salle)
    block_minutes: float = 0.0      # durée de blocage de la salle
    pacu_start: float = None        # entrée en SSPI
    departure: float = None         # sortie définitive
    turnover_end: float = None      # fin de nettoyage -> salle libérée

    def priority_key(self):
        # Les urgences passent avant les cas programmés ; sinon ordre d'arrivée.
        return (0 if self.kind == "emergency" else 1, self.arrival, self.cid)


@dataclass
class RoomBlock:
    """Occupation d'une salle SANS patient : QA matinale ou maintenance.
    Passe en priorité absolue pour la prochaine salle libre (on n'interrompt
    jamais une chirurgie en cours, mais la maintenance prend la main ensuite)."""
    kind: str            # 'qa' ou 'maintenance'
    duration: float
    seize_start: float = None

    def priority_key(self):
        return (-1, 0.0, 0)   # avant tout le reste


# ---------------------------------------------------------------------------
# 3. LE MOTEUR À ÉVÉNEMENTS DISCRETS
# ---------------------------------------------------------------------------
class ORSimulation:
    def __init__(self, cfg: Config, seed: int):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.now = 0.0
        self._heap = []                 # file d'événements : (temps, ordre, fonction)
        self._counter = itertools.count()

        self.rooms_available = cfg.n_or
        self.pacu_available = cfg.n_pacu

        # --- effectifs présents (pools par rôle) ---
        self.circ_available = cfg.n_circ
        self.scrub_available = cfg.n_scrub
        self.anes_available = cfg.n_anes
        self.active_teams = 0           # cas en cours (équipes mobilisées)
        self.peak_teams = 0             # pic de salles tournant en parallèle
        self.staff_idle_room_min = 0.0  # salle-min perdues faute de personnel
        self._last_t = 0.0

        self.or_queue: list = []        # file (heap) des cas attendant une salle
        self.pacu_wait: deque = deque() # cas BLOQUÉS en salle attendant un lit SSPI

        self.cases: list[Case] = []
        self._cid = itertools.count()
        self._qseq = itertools.count()  # ordre stable dans la file (objets non comparés)
        self.downtime_qa = 0.0          # minutes-salle de QA matinale
        self.downtime_maint = 0.0       # minutes-salle de maintenance préventive

    # --- mise en file (cas ou blocage de salle) ---
    def _enqueue(self, obj):
        heapq.heappush(self.or_queue, (obj.priority_key(), next(self._qseq), obj))

    # --- planification d'événements ---
    def schedule(self, delay: float, fn):
        heapq.heappush(self._heap, (self.now + delay, next(self._counter), fn))

    # --- création des cas ---
    def _new_case(self, kind: str, arrival: float) -> Case:
        c = Case(
            cid=next(self._cid),
            kind=kind,
            arrival=arrival,
            surgery_dur=draw_lognormal(self.rng, self.cfg.surgery_mean, self.cfg.surgery_std),
            recovery_dur=draw_lognormal(self.rng, self.cfg.recovery_mean, self.cfg.recovery_std),
        )
        self.cases.append(c)
        return c

    # --- arrivées ---
    def arrive_elective_batch(self):
        # Tous les cas programmés sont admis et prêts à l'ouverture du bloc.
        for _ in range(self.cfg.n_elective):
            c = self._new_case("elective", self.now)
            self._enqueue(c)
        self.try_start_or()

    def arrive_emergency(self, case: Case):
        self._enqueue(case)
        self.try_start_or()

    # --- maintenance / QA : occupation d'une salle sans patient ---
    def schedule_morning_qa(self):
        """Au démarrage, chaque salle subit un contrôle/calibration (QA)."""
        if self.cfg.morning_qa_time <= 0:
            return
        for _ in range(self.cfg.n_or):
            self._enqueue(RoomBlock("qa", self.cfg.morning_qa_time))
        self.try_start_or()

    def trigger_maintenance(self):
        """Une salle est retirée du circuit pour maintenance préventive."""
        self._enqueue(RoomBlock("maintenance", self.cfg.maint_dur))
        self.try_start_or()

    # --- coeur logique : affecter les salles disponibles ---
    def _can_start(self, obj) -> bool:
        if self.rooms_available <= 0:
            return False
        if isinstance(obj, RoomBlock):
            return True                 # QA/maintenance : pas d'équipe clinique
        # NIVEAU 3 : un cas exige aussi une équipe complète
        if self.cfg.use_personnel:
            return (self.circ_available > 0 and self.scrub_available > 0
                    and self.anes_available > 0)
        return True

    def try_start_or(self):
        # On regarde le job prioritaire SANS le retirer ; on ne l'engage que si
        # toutes les ressources sont là. Les RoomBlock (QA/maintenance) passent
        # devant et ne consomment qu'une salle.
        while self.or_queue:
            obj = self.or_queue[0][2]          # peek
            if not self._can_start(obj):
                break
            heapq.heappop(self.or_queue)
            self.rooms_available -= 1
            obj.seize_start = self.now
            if isinstance(obj, RoomBlock):
                self.schedule(obj.duration, lambda b=obj: self.on_block_end(b))
            else:
                if self.cfg.use_personnel:      # NIVEAU 3 : mobilise l'équipe
                    self.circ_available -= 1
                    self.scrub_available -= 1
                    self.anes_available -= 1
                self.active_teams += 1
                self.peak_teams = max(self.peak_teams, self.active_teams)
                dur = self.cfg.induction_time + obj.surgery_dur
                self.schedule(dur, lambda c=obj: self.on_surgery_end(c))

    def on_block_end(self, block: RoomBlock):
        if block.kind == "qa":
            self.downtime_qa += block.duration
        else:
            self.downtime_maint += block.duration
        self.rooms_available += 1
        self.try_start_or()

    def on_surgery_end(self, case: Case):
        case.surgery_end = self.now
        self.active_teams -= 1
        if self.cfg.use_personnel:              # NIVEAU 3 : libère l'équipe
            self.circ_available += 1
            self.scrub_available += 1
            self.anes_available += 1

        if not self.cfg.use_sspi:
            # NIVEAU 1 : pas de réveil modélisé -> le patient sort directement,
            # la salle est nettoyée puis libérée.
            case.departure = self.now
            self.schedule(self.cfg.turnover_time, self.on_turnover_end)
            case.turnover_end = self.now + self.cfg.turnover_time
        elif self.pacu_available > 0:
            # NIVEAU 2 : un lit de réveil est libre
            self._start_recovery(case)
            self.schedule(self.cfg.turnover_time, self.on_turnover_end)
            case.turnover_end = self.now + self.cfg.turnover_time
        else:
            # NIVEAU 2 : AUCUN lit SSPI -> le patient reste dans la salle : BLOCAGE
            case.block_start = self.now
            self.pacu_wait.append(case)
        # une équipe / salle vient de se libérer : un cas en attente peut partir
        self.try_start_or()

    def _start_recovery(self, case: Case):
        self.pacu_available -= 1
        case.pacu_start = self.now
        self.schedule(case.recovery_dur, lambda c=case: self.on_recovery_end(c))

    def on_recovery_end(self, case: Case):
        case.departure = self.now
        self.pacu_available += 1
        # Priorité : libérer une salle bloquée en lui donnant le lit qui se libère.
        if self.pacu_wait:
            nxt = self.pacu_wait.popleft()
            nxt.block_minutes = self.now - nxt.block_start
            self._start_recovery(nxt)
            # la salle de ce patient peut enfin être nettoyée puis libérée
            self.schedule(self.cfg.turnover_time, self.on_turnover_end)
            nxt.turnover_end = self.now + self.cfg.turnover_time

    def on_turnover_end(self):
        self.rooms_available += 1
        self.try_start_or()

    # --- exécution ---
    def run(self):
        # NIVEAU 4 : QA matinale + maintenance préventive (sinon ignorés)
        if self.cfg.use_maintenance:
            self.schedule_morning_qa()
            if self.rng.random() < self.cfg.maint_proba:
                start = float(self.rng.uniform(30.0, self.cfg.arrival_window * 0.5))
                self.schedule(start, self.trigger_maintenance)
        # cas programmés à t=0
        self.schedule(0.0, self.arrive_elective_batch)
        # urgences : arrivées poissoniennes sur la fenêtre de la journée
        t = self.rng.exponential(self.cfg.emergency_interarrival_mean)
        while t <= self.cfg.arrival_window:
            arrival_t = t
            c = self._new_case("emergency", arrival_t)
            self.schedule(arrival_t, lambda c=c: self.arrive_emergency(c))
            t += self.rng.exponential(self.cfg.emergency_interarrival_mean)

        # boucle : on saute d'événement en événement jusqu'à épuisement
        while self._heap:
            time, _, fn = heapq.heappop(self._heap)
            dt = time - self._last_t
            if dt > 0:
                self._accrue_staff_idle(dt)
            self._last_t = time
            self.now = time
            fn()

        return self._compute_metrics()

    def _accrue_staff_idle(self, dt: float):
        """Cumule les salle-minutes perdues parce qu'une salle est libre et un
        cas attend, mais qu'il manque du personnel pour ouvrir."""
        staff_short = (self.circ_available <= 0 or self.scrub_available <= 0
                       or self.anes_available <= 0)
        if self.rooms_available > 0 and staff_short:
            qc = sum(1 for item in self.or_queue if isinstance(item[2], Case))
            if qc > 0:
                self.staff_idle_room_min += min(self.rooms_available, qc) * dt

    # --- indicateurs de sortie (KPIs) ---
    def _compute_metrics(self) -> dict:
        cfg = self.cfg
        close = cfg.scheduled_close
        done = [c for c in self.cases if c.departure is not None]

        makespan = max(c.departure for c in done)
        productive = sum((c.surgery_end - c.seize_start) for c in done)  # induction+chirurgie
        total_block = sum(c.block_minutes for c in done)
        n_blocked = sum(1 for c in done if c.block_minutes > 0)

        # heures sup = minutes-salle occupées au-delà de l'heure de fermeture
        overtime = 0.0
        for c in done:
            end = c.turnover_end if c.turnover_end is not None else c.departure
            overtime += max(0.0, end - max(close, c.seize_start))

        waits = [c.seize_start - c.arrival for c in done]
        emerg_waits = [c.seize_start - c.arrival for c in done if c.kind == "emergency"]

        return {
            "salles": cfg.n_or,
            "lits_sspi": cfg.n_pacu,
            "cas_total": len(done),
            "makespan_min": makespan,
            "occupation_salle_%": 100.0 * productive / (cfg.n_or * makespan),
            "blocage_sspi_min": total_block,
            "cas_bloques": n_blocked,
            "heures_sup_min": overtime,
            "attente_moy_salle_min": float(np.mean(waits)),
            "attente_urgences_min": float(np.mean(emerg_waits)) if emerg_waits else 0.0,
            "downtime_qa_min": self.downtime_qa,
            "downtime_maint_min": self.downtime_maint,
            "pic_equipes": float(self.peak_teams),
            "salle_min_perdues_personnel": self.staff_idle_room_min,
        }


# ---------------------------------------------------------------------------
# 4. EXPÉRIMENTATION : comparer plusieurs scénarios sur N répétitions
# ---------------------------------------------------------------------------
def run_scenario(cfg: Config) -> dict:
    """Lance n_replications simulations et renvoie la moyenne des KPIs."""
    keys = ["makespan_min", "occupation_salle_%", "blocage_sspi_min",
            "cas_bloques", "heures_sup_min", "attente_moy_salle_min",
            "attente_urgences_min", "cas_total",
            "downtime_qa_min", "downtime_maint_min",
            "pic_equipes", "salle_min_perdues_personnel"]
    acc = {k: [] for k in keys}
    for r in range(cfg.n_replications):
        m = ORSimulation(cfg, seed=cfg.base_seed + r).run()
        for k in keys:
            acc[k].append(m[k])
    out = {"salles": cfg.n_or, "lits_sspi": cfg.n_pacu}
    out.update({k: float(np.mean(v)) for k, v in acc.items()})
    return out


# ---------------------------------------------------------------------------
# 4bis. DIMENSIONNEMENT DES EFFECTIFS (méthode EPT + facteur de couverture)
# ---------------------------------------------------------------------------
def effectifs_a_recruter(salles_jour: int, personnes_par_salle: float = 2.0,
                         heures_jour: float = 9.0, jours_semaine: int = 5,
                         heures_ept_semaine: float = 42.0,
                         facteur_couverture: float = 1.27) -> dict:
    """Traduit un besoin 'au sol' en EPT à recruter (méthode type AORN).

    salles_jour          : nb de salles tenues simultanément en journée
    personnes_par_salle  : ex. 2 (circulant + instrumentiste), 3 avec anesthésie
    heures_ept_semaine   : semaine contractuelle d'un EPT (Suisse ~42 h)
    facteur_couverture   : 1 / disponibilité nette (vacances+maladie+formation).
                           Suisse ~1.25-1.30 ; repère US ~1.14.
    """
    heures_a_couvrir = salles_jour * heures_jour * jours_semaine        # étape 1
    heures_travail = heures_a_couvrir * personnes_par_salle             # étape 2
    ept_base = heures_travail / heures_ept_semaine                      # étape 3
    ept_a_recruter = ept_base * facteur_couverture                     # étapes 4-5
    return {
        "ept_base_au_sol": ept_base,
        "ept_a_recruter": ept_a_recruter,
        "remplacement_ept": ept_a_recruter - ept_base,
    }


def fmt_clock(minutes: float) -> str:
    """Convertit des minutes après 08:00 en heure d'horloge."""
    total = 8 * 60 + minutes
    h, m = divmod(int(round(total)), 60)
    return f"{h:02d}:{m:02d}"


def main():
    scenarios = {
        "A. Référence (4 salles, 3 SSPI)": Config(n_or=4, n_pacu=3),
        "B. +1 salle    (5 salles, 3 SSPI)": Config(n_or=5, n_pacu=3),
        "C. +2 lits SSPI(4 salles, 5 SSPI)": Config(n_or=4, n_pacu=5),
    }

    results = {name: run_scenario(cfg) for name, cfg in scenarios.items()}

    # ---- tableau comparatif ----
    print("\n" + "=" * 78)
    print(" SIMULATION DU BLOC OPÉRATOIRE — comparaison de scénarios")
    print(" (moyennes sur 40 répétitions, ouverture 08:00, fermeture prévue 16:00)")
    print("=" * 78)
    header = f"{'Scénario':<34}{'Occup.':>8}{'Blocage':>9}{'H.sup':>8}{'Att.sal':>9}{'Fin':>8}"
    print(header)
    print(f"{'':<34}{'salle':>8}{'SSPI':>9}{'(min)':>8}{'(min)':>9}{'(8h+)':>8}")
    print("-" * 78)
    for name, r in results.items():
        print(f"{name:<34}"
              f"{r['occupation_salle_%']:>7.1f}%"
              f"{r['blocage_sspi_min']:>9.0f}"
              f"{r['heures_sup_min']:>8.0f}"
              f"{r['attente_moy_salle_min']:>8.0f}m"
              f"{fmt_clock(r['makespan_min']):>8}")
    print("=" * 78)

    # ---- lecture ----
    a, b, c = results.values()
    print("\nLECTURE :")
    print(f"  • Référence A : {a['blocage_sspi_min']:.0f} min de salles bloquées par manque")
    print(f"    de lit de réveil, dernier patient sorti à {fmt_clock(a['makespan_min'])}.")
    print(f"  • Ajouter une SALLE (B) : blocage {b['blocage_sspi_min']:.0f} min, "
          f"fin {fmt_clock(b['makespan_min'])} -> peu d'amélioration,")
    print(f"    car le vrai goulot est en AVAL (la SSPI), pas le nombre de salles.")
    print(f"  • Ajouter des LITS DE SSPI (C) : blocage {c['blocage_sspi_min']:.0f} min, "
          f"fin {fmt_clock(c['makespan_min'])}")
    print(f"    -> le débit se débloque pour un investissement souvent moindre.")
    print("\n  => Le bloc n'est pas toujours le goulot. La simulation le révèle.\n")

    # ---- graphique ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        names = ["A\n4 sal / 3 SSPI", "B\n5 sal / 3 SSPI", "C\n4 sal / 5 SSPI"]
        block = [r["blocage_sspi_min"] for r in results.values()]
        overt = [r["heures_sup_min"] for r in results.values()]
        occup = [r["occupation_salle_%"] for r in results.values()]

        fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
        colors = ["#c0392b", "#e67e22", "#27ae60"]

        axes[0].bar(names, block, color=colors)
        axes[0].set_title("Blocage des salles\n(min, attente lit SSPI)")
        axes[0].set_ylabel("minutes")

        axes[1].bar(names, overt, color=colors)
        axes[1].set_title("Heures supplémentaires\n(min au-delà de 16:00)")

        axes[2].bar(names, occup, color=colors)
        axes[2].set_title("Taux d'occupation\nproductif des salles (%)")
        axes[2].set_ylim(0, 100)

        for ax in axes:
            ax.grid(axis="y", alpha=0.3)
            ax.spines[["top", "right"]].set_visible(False)

        fig.suptitle("Bloc opératoire : l'effet du goulot d'aval (SSPI)", fontweight="bold")
        fig.tight_layout()
        fig.savefig("bloc_resultats.png", dpi=130, bbox_inches="tight")
        print("Graphique enregistré : bloc_resultats.png")
    except Exception as e:
        print(f"(graphique non généré : {e})")


if __name__ == "__main__":
    main()
