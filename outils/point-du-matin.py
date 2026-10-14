#!/usr/bin/env python3
"""Point du matin : collecte des chiffres et génération d'une page HTML au format fixe.

Usage :
  point-du-matin.py collecte            Récupère météo, vigilances (MeteoAlarm), indices et
                                        matières (Yahoo Finance), alertes GDACS, cryptos,
                                        séismes et devises (API sans clé), les met en cache pour la journée
                                        et affiche un résumé JSON à utiliser pour rédiger.
  point-du-matin.py modele              Affiche le modèle JSON de rédaction à remplir.
  point-du-matin.py rappels             Affiche les rappels dus (non faits) de ~/claude/rappels.json.
  point-du-matin.py publier FICHIER     Valide la rédaction JSON, génère la page du jour,
                                        écrit les titres pour la notification de démarrage,
                                        envoie une notification et ouvre la page. Les rappels
                                        traités avec le statut « regle » passent à "fait": true.
       options : --sans-ouvrir  --sans-notif
  point-du-matin.py partager FR.json EN.json --profil sierra-leone
                                        Publie la page du jour en ligne (GitHub Pages), en français et en
                                        anglais, sans liens locaux, puis pousse le dépôt keuzere.github.io.
  Toutes les commandes : --profil france|sierra-leone (défaut : france ; le profil sierra-leone écrit dans
  le sous-dossier sierra-leone/, avec ses villes, ses rubriques et ses chiffres).

Fichiers (dossier ~/.local/share/point-du-matin/) :
  AAAA-MM-JJ.html  page du jour (archive, 60 jours)    index.html  dernière page
  donnees-AAAA-MM-JJ.json  cache des chiffres    redaction-AAAA-MM-JJ.json  rédaction (lue par approfondir.py)
Titres : ~/.local/state/point-du-matin/AAAA-MM-JJ.txt (lu par notif-point-du-matin.sh)

Relançable sans effet de bord : chaque commande réécrit les mêmes fichiers du jour.
Bibliothèque standard uniquement.
"""
import datetime as dt
import html
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path.home()
DOSSIER = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "point-du-matin"
ETAT = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "point-du-matin"
ARCHIVE_JOURS = 60
SERVEUR_LOCAL = "http://127.0.0.1:8787"  # service systemd point-du-matin-pages (scripts/systemd/)
DOSSIER_TRAVAIL = Path(os.environ.get("POINT_DU_MATIN_DOSSIER_CLAUDE", HOME / "claude"))
RAPPELS = DOSSIER_TRAVAIL / "rappels.json"  # liste de {"id", "date" AAAA-MM-JJ, "texte", "fait"}

MARCHES_FRANCE = [  # (nom affiché, symbole Yahoo Finance, genre)
    ("CAC 40", "^FCHI", "indice"), ("Euro Stoxx 50", "^STOXX50E", "indice"), ("DAX", "^GDAXI", "indice"),
    ("S&P 500", "^GSPC", "indice"), ("Nasdaq", "^IXIC", "indice"), ("Dow Jones", "^DJI", "indice"),
    ("Nikkei", "^N225", "indice"), ("Brent", "BZ=F", "matiere"), ("Or (once)", "GC=F", "matiere"),
]

# Profils : un point du matin par public. Choisi par l'option --profil (défaut : france).
PROFILS = {
    "france": {
        "titre": "☀️ Point du matin", "sous_dossier": "", "fuseau": "Europe/Paris",
        "villes": [
            {"nom": "Montpellier", "dept": "Hérault (34)", "lat": 43.61, "lon": 3.88},
            {"nom": "Challans", "dept": "Vendée (85)", "lat": 46.85, "lon": -1.88},
        ],
        "sections": [  # ordre d'affichage fixe
            ("finance", "💶", "Finance et économie"),
            ("catastrophes", "🌋", "Catastrophes et alertes"),
            ("geopolitique", "🌍", "Guerres et géopolitique"),
            ("tech_ia", "🤖", "Tech et IA"),
            ("sciences_sante", "🔬", "Sciences et santé"),
        ],
        "collectes": ("meteo", "vigilances", "marches", "gdacs", "cryptos", "seismes", "devises"),
        "marches": MARCHES_FRANCE,
        "blocs": {"finance": ("marches", "devises", "cryptos"), "catastrophes": ("seismes", "gdacs")},
        "pays_gdacs": None,  # toutes les alertes orange et rouges
        "rappels": True,
        "replies": (),  # rubriques affichées en titres seuls, détail dépliable
        "facultatives": (),  # rubriques qui peuvent rester vides
        "meteo_compacte": False,
        "jours_meteo": 2,
    },
    "sierra-leone": {
        "titre": "🇸🇱 Point du matin — Sierra Leone", "sous_dossier": "sierra-leone", "fuseau": "Africa/Freetown",
        "villes": [
            {"nom": "Freetown", "dept": "Zone Ouest", "lat": 8.48, "lon": -13.23},
            {"nom": "Bo", "dept": "Province du Sud", "lat": 7.96, "lon": -11.74},
            {"nom": "Kenema", "dept": "Province de l'Est", "lat": 7.88, "lon": -11.19},
            {"nom": "Makeni", "dept": "Province du Nord", "lat": 8.88, "lon": -12.04},
        ],
        "sections": [
            ("or", "🥇", "Or : mines, prix, exportations"),
            ("sierra_leone", "🇸🇱", "Sierra Leone : politique, justice, institutions"),
            ("lois", "🏛️", "Lois, Journal officiel et mines"),
            ("economie", "💰", "Économie, prix et ressources"),
            ("societe", "👥", "Société, santé, éducation, vie locale"),
            ("expatries", "🧳", "Expatriés : sécurité et vie pratique"),
            ("voisins", "🧭", "Pays voisins et région"),
            ("monde", "🌐", "Le monde en bref"),
        ],
        "collectes": ("meteo", "marches", "gdacs", "devises_sle", "conseils"),
        "marches": [("Minerai de fer", "TIO=F", "matiere"), ("Or (once)", "GC=F", "matiere"),
                    ("Riz (cwt)", "ZR=F", "matiere"), ("Cacao (t)", "CC=F", "matiere"), ("Brent", "BZ=F", "matiere")],
        "blocs": {"or": ("cours_or",), "economie": ("marches", "devises"), "monde": ("gdacs",),
                  "expatries": ("conseils",)},
        # alertes de la région ; ailleurs, seulement les rouges
        "pays_gdacs": ("Sierra Leone", "Guinea", "Liberia", "Ivory Coast", "Côte d'Ivoire", "Senegal",
                       "Gambia", "Guinea-Bissau", "Mali"),
        "rappels": False,
        "public": "salone-2f993d",  # dossier du site public (partager)
        # pages publiques chiffrées par StatiCrypt ; sel fixe (non secret) pour que « se souvenir de moi » tienne d'un jour à l'autre
        "chiffrement": {"sel": "6fc64e7a1e8487898498d79b2487bea0",
                        "fichier_mdp": "~/.config/point-du-matin/mot-de-passe-sierra-leone"},
        "replies": ("or", "sierra_leone", "lois", "economie", "societe", "expatries", "voisins", "monde"),
        "facultatives": ("or", "lois", "expatries"),
        "meteo_compacte": True,
        "jours_meteo": 7,  # tendance de la semaine
    },
}
P = PROFILS["france"]
VILLES = P["villes"]
SECTIONS = P["sections"]


def maintenant_local():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(P["fuseau"]))


def appliquer_profil(nom):
    """Bascule les réglages globaux (villes, rubriques, dossiers) sur le profil demandé."""
    global P, VILLES, SECTIONS, DOSSIER, ETAT
    P = PROFILS[nom]
    VILLES, SECTIONS = P["villes"], P["sections"]
    if P["sous_dossier"]:
        DOSSIER, ETAT = DOSSIER / P["sous_dossier"], ETAT / P["sous_dossier"]

CODES_METEO = {
    0: ("☀️", "Ciel clair"), 1: ("🌤️", "Plutôt dégagé"), 2: ("⛅", "Partiellement nuageux"),
    3: ("☁️", "Couvert"), 45: ("🌫️", "Brouillard"), 48: ("🌫️", "Brouillard givrant"),
    51: ("🌦️", "Bruine légère"), 53: ("🌦️", "Bruine"), 55: ("🌧️", "Bruine forte"),
    56: ("🌧️", "Bruine verglaçante"), 57: ("🌧️", "Bruine verglaçante forte"),
    61: ("🌦️", "Pluie faible"), 63: ("🌧️", "Pluie"), 65: ("🌧️", "Pluie forte"),
    66: ("🌧️", "Pluie verglaçante"), 67: ("🌧️", "Pluie verglaçante forte"),
    71: ("🌨️", "Neige faible"), 73: ("🌨️", "Neige"), 75: ("❄️", "Neige forte"), 77: ("🌨️", "Grains de neige"),
    80: ("🌦️", "Averses faibles"), 81: ("🌧️", "Averses"), 82: ("⛈️", "Averses violentes"),
    85: ("🌨️", "Averses de neige"), 86: ("❄️", "Fortes averses de neige"),
    95: ("⛈️", "Orages"), 96: ("⛈️", "Orages avec grêle"), 99: ("⛈️", "Orages violents avec grêle"),
}

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

def modele():
    """Structure JSON de rédaction à remplir, selon le profil."""
    m = {
        "en_bref": ["5 titres courts, les plus importants du jour, tous thèmes confondus"],
        "meteo": {"commentaire": "2-3 phrases : ce qu'il faut retenir pour " + ", ".join(v["nom"] for v in VILLES)},
        "marches": {"commentaire": "Pourquoi les marchés et les prix ont bougé, en clair"},
        "sections": {
            cle: [{"titre": "Titre", "texte": "2 à 5 phrases, termes techniques expliqués",
                   "pourquoi": "Pourquoi c'est important (une phrase, facultatif)",
                   "importance": "haute|normale",
                   "impact_economique": "Effets sur l'économie de la zone (facultatif)",
                   "fiabilite": "confirme|une_source|analyse",
                   "sources": [{"nom": "Le Monde", "url": "https://…", "date": "03/10 08:12"}]}]
            for cle, _, _ in SECTIONS
        },
        "agenda": [{"date": "mar. 06/10", "evenement": "Réunion de la BCE"}],
        "notes": ["Facultatif : source en panne, chiffre contesté…"],
    }
    if "vigilances" in P["collectes"]:
        m["meteo"]["vigilances"] = [{"departement": "Hérault", "niveau": "vert|jaune|orange|rouge",
                                     "phenomene": "orages, pluie-inondation…",
                                     "source": {"nom": "Météo-France", "url": "https://…"}}]
    m["marches"]["indices"] = [{"nom": "CAC 40", "valeur": "8 123,45", "variation_pct": 0.42}]
    m["marches"]["matieres"] = [{"nom": "Gazole", "valeur": "1,72 €", "variation_pct": -1.2}]
    if "catastrophes" in dict((c, 1) for c, _, _ in SECTIONS):
        m["sections"]["catastrophes"][0]["inondation_majeure"] = "true/false (facultatif ; impact_economique obligatoire si true)"
    if "lois" in m["sections"]:
        m["sections"]["lois"][0].update({
            "titre": "Titre qui annonce la couleur (ce qui change, pour qui)",
            "domaine": "mines|finance|politique|entreprises",
            "statut": "publié au Journal officiel|voté au Parlement|déposé au Parlement|annoncé|contesté en justice",
            "reference": "Nom exact du texte et numéro (Act No. …, Statutory Instrument No. …), si connu"})
    if P["rappels"]:
        m["rappels"] = [{"id": "id du rappel dû (voir la commande rappels)", "statut": "regle|en_attente",
                         "reponse": "Ce que la vérification a trouvé, 1 à 3 phrases",
                         "sources": [{"nom": "ESA", "url": "https://…", "date": "03/10"}]}]
    return m


# ---------------------------------------------------------------- collecte

def _get_json(url, timeout=20, essais=3):
    """Lecture JSON avec nouvelles tentatives sur les pannes passagères (503, 429, délai dépassé)."""
    import time
    req = urllib.request.Request(url, headers={"User-Agent": "point-du-matin/1.0"})
    for n in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as ex:
            passagere = not isinstance(ex, urllib.error.HTTPError) or ex.code in (429, 500, 502, 503, 504)
            if not passagere or n == essais - 1:
                raise
            time.sleep(4 * (n + 1))


def _essayer(nom, fonction, erreurs):
    try:
        return fonction()
    except Exception as e:  # une source en panne ne doit pas bloquer la page
        erreurs.append(f"{nom} : {e}")
        return None


def collecter_meteo_toutes(villes):
    """Toutes les villes en une seule requête (Open-Meteo limite le nombre d'appels par adresse IP)."""
    url = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
           "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset"
           "&hourly=temperature_2m,precipitation_probability,precipitation"
           "&timezone={fuseau}&forecast_days={jours}").format(
        lat=",".join(str(v["lat"]) for v in villes), lon=",".join(str(v["lon"]) for v in villes),
        jours=P["jours_meteo"], fuseau=urllib.parse.quote(P["fuseau"], safe=""))
    reponses = _get_json(url)
    if isinstance(reponses, dict):  # une seule ville : objet au lieu de liste
        reponses = [reponses]
    return [_meteo_ville(v, d) for v, d in zip(villes, reponses)]


def _meteo_ville(ville, d):
    jours = [{k: d["daily"][k][i] for k in d["daily"]} for i in range(len(d["daily"]["time"]))]
    heures = [{"h": t[11:16], "temp": d["hourly"]["temperature_2m"][i],
               "proba_pluie": d["hourly"]["precipitation_probability"][i],
               "pluie_mm": d["hourly"]["precipitation"][i]}
              for i, t in enumerate(d["hourly"]["time"][:24])]
    return {"ville": ville["nom"], "dept": ville["dept"], "jours": jours, "heures": heures}


def collecter_meteo(ville):
    url = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
           "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset"
           "&hourly=temperature_2m,precipitation_probability,precipitation"
           "&timezone={fuseau}&forecast_days={jours}").format(jours=P["jours_meteo"], fuseau=urllib.parse.quote(P["fuseau"], safe=""), **ville)
    d = _get_json(url)
    jours = []
    for i in range(len(d["daily"]["time"])):
        jours.append({k: d["daily"][k][i] for k in d["daily"]})
    heures = [{"h": t[11:16], "temp": d["hourly"]["temperature_2m"][i],
               "proba_pluie": d["hourly"]["precipitation_probability"][i],
               "pluie_mm": d["hourly"]["precipitation"][i]}
              for i, t in enumerate(d["hourly"]["time"][:24])]
    return {"ville": ville["nom"], "dept": ville["dept"], "jours": jours, "heures": heures}


def collecter_cryptos():
    d = _get_json("https://api.coingecko.com/api/v3/coins/markets?vs_currency=eur"
                  "&order=market_cap_desc&per_page=10&sparkline=true"
                  "&price_change_percentage=24h,7d")
    return [{"nom": c["name"], "symbole": c["symbol"].upper(), "prix": c["current_price"],
             "var_24h": c.get("price_change_percentage_24h_in_currency"),
             "var_7j": c.get("price_change_percentage_7d_in_currency"),
             "capitalisation": c.get("market_cap"),
             "courbe_7j": (c.get("sparkline_in_7d") or {}).get("price", [])[::4]}
            for c in d]


def collecter_seismes():
    d = _get_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
    sortie = []
    for f in d["features"]:
        p = f["properties"]
        if (p.get("mag") or 0) >= 5:
            sortie.append({"magnitude": p["mag"], "lieu": p["place"], "url": p["url"],
                           "heure": dt.datetime.fromtimestamp(p["time"] / 1000).strftime("%d/%m %H:%M"),
                           "tsunami": bool(p.get("tsunami")), "alerte": p.get("alert")})
    return sorted(sortie, key=lambda s: -s["magnitude"])


def collecter_devises():
    d = _get_json("https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD,GBP,CHF,JPY")
    return {"date": d["date"], "taux": d["rates"]}


def collecter_devises_sle():
    """Valeur en leones (SLE) des devises utiles, d'après le taux officiel indicatif (open.er-api.com)."""
    d = _get_json("https://open.er-api.com/v6/latest/SLE")
    taux = {k: round(1 / d["rates"][k], 4) for k in ("USD", "EUR", "GBP", "GNF", "LRD", "XOF") if d["rates"].get(k)}
    return {"date": dt.datetime.fromtimestamp(d["time_last_update_unix"], dt.timezone.utc).strftime("%Y-%m-%d"),
            "taux": taux, "base": "SLE"}


DEVISES_SYMBOLE = {"USD": "$", "EUR": "€", "JPY": "¥", "GBP": "£"}


def collecter_cours(nom, symbole, genre):
    """Dernière clôture (ou cours en séance) et variation par rapport à la clôture précédente."""
    d = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/"
                  + urllib.parse.quote(symbole) + "?range=5d&interval=1d")["chart"]["result"][0]
    points = [(t, c) for t, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]) if c is not None]
    (t, valeur), prec = points[-1], (points[-2][1] if len(points) >= 2 else None)
    unite = "" if genre == "indice" else " " + DEVISES_SYMBOLE.get(d["meta"].get("currency"), d["meta"].get("currency", ""))
    return {"nom": nom, "genre": genre, "valeur": nombre(valeur, 2) + unite,
            "variation_pct": round((valeur / prec - 1) * 100, 2) if prec else None,
            "date": dt.datetime.fromtimestamp(t).strftime("%d/%m")}


def collecter_marches(erreurs):
    return [c for c in (_essayer(f"Yahoo Finance {n}", lambda a=(n, s, g): collecter_cours(*a), erreurs)
                        for n, s, g in P["marches"]) if c]


def collecter_conseils():
    """Dernière mise à jour des conseils aux voyageurs britanniques et dernière alerte de l'ambassade américaine."""
    import xml.etree.ElementTree as ET
    uk = _get_json("https://www.gov.uk/api/content/foreign-travel-advice/sierra-leone")
    sortie = [{"source": "Royaume-Uni (FCDO)", "date": str(uk.get("public_updated_at", ""))[:10],
               "texte": uk.get("details", {}).get("change_description", "").strip(),
               "url": "https://www.gov.uk/foreign-travel-advice/sierra-leone"}]
    req = urllib.request.Request("https://sl.usembassy.gov/category/alert/feed/",
                                 headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=20) as r:
        item = ET.fromstring(r.read()).find("channel/item")
    if item is not None:
        quand = dt.datetime.strptime(item.findtext("pubDate", "")[:16], "%a, %d %b %Y")
        sortie.append({"source": "Ambassade des États-Unis", "date": quand.strftime("%Y-%m-%d"),
                       "texte": html.unescape(item.findtext("title", "")), "url": item.findtext("link", "")})
    return sortie


GDACS_TYPES = {"EQ": "Séisme", "TC": "Cyclone", "FL": "Inondation", "VO": "Éruption",
               "DR": "Sécheresse", "WF": "Feux de forêt"}


def collecter_gdacs(aujourdhui):
    """Alertes orange et rouges de GDACS en cours ou terminées depuis moins de 3 jours."""
    d = _get_json("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
                  "?alertlevel=Orange;Red&eventlist=EQ;TC;FL;VO;DR;WF")
    limite = (aujourdhui - dt.timedelta(days=3)).isoformat()
    sortie = []
    for f in d.get("features", []):
        p = f["properties"]
        if p.get("iscurrent") != "true" and str(p.get("todate", ""))[:10] < limite:
            continue
        pays = str(p.get("country") or "").strip(" ,")
        if P["pays_gdacs"] and p.get("alertlevel") != "Red" and not any(x in pays for x in P["pays_gdacs"]):
            continue
        sortie.append({"niveau": {"Red": "rouge", "Orange": "orange"}.get(p.get("alertlevel"), p.get("alertlevel")),
                       "type": GDACS_TYPES.get(p.get("eventtype"), p.get("eventtype")),
                       "nom": p.get("name") if len(p.get("name") or "") <= 60 else p["name"][:57] + "…", "pays": pays if len(pays) <= 120 else pays[:117] + "…",
                       "debut": str(p.get("fromdate", ""))[:10], "fin": str(p.get("todate", ""))[:10],
                       "en_cours": p.get("iscurrent") == "true",
                       "gravite": (p.get("severitydata") or {}).get("severitytext"),
                       "url": (p.get("url") or {}).get("report")})
    return sorted(sortie, key=lambda a: (a["niveau"] != "rouge", not a["en_cours"], a["fin"]))


CAP_NIVEAUX = {"Minor": "vert", "Moderate": "jaune", "Severe": "orange", "Extreme": "rouge"}
CAP_PHENOMENES = [("thunderstorm", "orages"), ("flood", "pluie-inondation"), ("rain", "pluie-inondation"),
                  ("wind", "vent violent"), ("snow", "neige-verglas"), ("ice", "neige-verglas"),
                  ("high-temperature", "canicule"), ("low-temperature", "grand froid"),
                  ("coastal", "vagues-submersion"), ("avalanche", "avalanches"), ("fog", "brouillard"),
                  ("forest-fire", "feux de forêt")]


def collecter_vigilances():
    """Vigilances jaunes et plus des départements suivis, d'après le flux MeteoAlarm de la France.
    Liste vide : aucune vigilance en cours (le flux ne publie que le jaune et au-delà)."""
    import xml.etree.ElementTree as ET
    req = urllib.request.Request("https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-france",
                                 headers={"User-Agent": "point-du-matin/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        racine = ET.fromstring(r.read())
    ns = {"a": "http://www.w3.org/2005/Atom", "cap": "urn:oasis:names:tc:emergency:cap:1.2"}
    suivis = {v["dept"].split(" (")[0] for v in VILLES}
    maintenant = dt.datetime.now(dt.timezone.utc)
    sortie, vus = [], set()
    for en in racine.findall("a:entry", ns):
        zone = en.findtext("cap:areaDesc", "", ns).strip()
        if zone not in suivis:
            continue
        try:
            if dt.datetime.fromisoformat(en.findtext("cap:expires", "", ns)) < maintenant:
                continue
        except ValueError:
            pass
        evenement = en.findtext("cap:event", "", ns).lower()
        phenomene = next((fr for cle, fr in CAP_PHENOMENES if cle in evenement), evenement)
        niveau = CAP_NIVEAUX.get(en.findtext("cap:severity", "", ns), "?")
        if (zone, niveau, phenomene) in vus:
            continue
        vus.add((zone, niveau, phenomene))
        sortie.append({"departement": zone, "niveau": niveau, "phenomene": phenomene,
                       "debut": en.findtext("cap:onset", "", ns)[:16], "fin": en.findtext("cap:expires", "", ns)[:16],
                       "source": {"nom": "MeteoAlarm", "url": "https://meteoalarm.org?region=FR"}})
    return sortie


def collecte(aujourdhui):
    erreurs = []
    donnees = {
        "date": aujourdhui.isoformat(),
        "collecte_a": maintenant_local().strftime("%H:%M"),
        # une requête pour toutes les villes ; à défaut, ville par ville
        "meteo": (_essayer("Météo (toutes les villes)", lambda: collecter_meteo_toutes(VILLES), [])
                  or [m for m in (_essayer(f"Météo {v['nom']}", lambda v=v: collecter_meteo(v), erreurs)
                                  for v in VILLES) if m]),
        "erreurs": erreurs,
    }
    c = P["collectes"]
    if "vigilances" in c:
        donnees["vigilances"] = _essayer("MeteoAlarm", collecter_vigilances, erreurs)
    if "marches" in c:
        donnees["marches"] = collecter_marches(erreurs)
    if "gdacs" in c:
        donnees["gdacs"] = _essayer("GDACS", lambda: collecter_gdacs(aujourdhui), erreurs)
    if "cryptos" in c:
        donnees["cryptos"] = _essayer("CoinGecko", collecter_cryptos, erreurs) or []
    if "seismes" in c:
        donnees["seismes"] = _essayer("USGS", collecter_seismes, erreurs) or []
    if "devises" in c:
        donnees["devises"] = _essayer("Frankfurter (BCE)", collecter_devises, erreurs)
    if "conseils" in c:
        donnees["conseils"] = _essayer("Conseils aux voyageurs", collecter_conseils, erreurs) or []
    if "devises_sle" in c:
        donnees["devises"] = _essayer("open.er-api.com (leone)", collecter_devises_sle, erreurs)
    donnees["rappels_dus"] = rappels_dus(aujourdhui)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / f"donnees-{aujourdhui}.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=1))
    return donnees


def resume_pour_redaction(d):
    """Version allégée (sans courbes ni heures) affichée à Claude pour rédiger."""
    r = json.loads(json.dumps(d))
    for m in r["meteo"]:
        m.pop("heures", None)
    for c in r.get("cryptos", []):
        c.pop("courbe_7j", None)
    return r


# ---------------------------------------------------------------- rappels

def lire_rappels():
    try:
        items = json.loads(RAPPELS.read_text(encoding="utf-8"))
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def rappels_dus(aujourdhui):
    if not P["rappels"]:
        return []
    return [r for r in lire_rappels()
            if isinstance(r, dict) and not r.get("fait") and str(r.get("date", "9999")) <= aujourdhui.isoformat()]


def clore_rappels(traites, aujourdhui):
    """Passe "fait": true aux rappels réglés ; ne réécrit le fichier que s'il y a un changement."""
    regles = {str(t.get("id")): t for t in traites if isinstance(t, dict) and t.get("statut") == "regle"}
    items = lire_rappels()
    change = False
    for r in items:
        t = regles.get(str(r.get("id")))
        if t and not r.get("fait"):
            r["fait"] = True
            r["fait_le"] = aujourdhui.isoformat()
            r["conclusion"] = t.get("reponse", "")
            change = True
    if change:
        RAPPELS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [str(r.get("id")) for r in items if str(r.get("id")) in regles]


# ---------------------------------------------------------------- validation

def valider(red, dus=()):
    pb = []
    if not isinstance(red, dict):
        return ["la racine doit être un objet JSON"]
    eb = red.get("en_bref")
    if not isinstance(eb, list) or not (3 <= len(eb) <= 7) or not all(isinstance(x, str) for x in eb):
        pb.append("en_bref : liste de 3 à 7 textes attendue (5 idéalement)")
    sec = red.get("sections")
    if not isinstance(sec, dict):
        pb.append("sections : objet attendu avec les clés " + ", ".join(c for c, _, _ in SECTIONS))
    else:
        for cle, _, _ in SECTIONS:
            items = sec.get(cle)
            if cle in P["facultatives"] and not items:
                continue
            if not isinstance(items, list) or not items:
                pb.append(f"sections.{cle} : au moins un élément attendu")
                continue
            for i, it in enumerate(items):
                if not isinstance(it, dict) or not it.get("titre") or not it.get("texte"):
                    pb.append(f"sections.{cle}[{i}] : 'titre' et 'texte' obligatoires")
                elif not it.get("sources"):
                    pb.append(f"sections.{cle}[{i}] ({it['titre'][:40]}) : au moins une source")
                elif it.get("inondation_majeure") is True and not it.get("impact_economique"):
                    pb.append(f"sections.{cle}[{i}] ({it['titre'][:40]}) : inondation majeure sans 'impact_economique'")
    for cle in ("meteo", "marches"):
        if cle in red and not isinstance(red[cle], dict):
            pb.append(f"{cle} : objet attendu")
    if "agenda" in red and not isinstance(red["agenda"], list):
        pb.append("agenda : liste attendue")
    traites = red.get("rappels") or []
    if not isinstance(traites, list):
        pb.append("rappels : liste attendue")
        traites = []
    ids = {str(t.get("id")) for t in traites if isinstance(t, dict)}
    for r in dus:
        if str(r.get("id")) not in ids:
            pb.append(f"rappels : le rappel dû « {r.get('id')} » n'est pas traité")
    for t in traites:
        if not isinstance(t, dict) or t.get("statut") not in ("regle", "en_attente") or not t.get("reponse"):
            pb.append("rappels : chaque élément demande 'id', 'statut' (regle|en_attente) et 'reponse'")
    return pb


# ---------------------------------------------------------------- rendu HTML

def e(x):
    return html.escape(str(x if x is not None else ""))


PUBLIC = False  # vrai pendant la génération des pages partagées en ligne (voir partager)


def lien(url, texte):
    url = str(url or "")
    if not url.startswith(("https://", "http://")) or (PUBLIC and "127.0.0.1" in url):
        return e(texte)
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(texte)}</a>'


def nombre(x, dec=2):
    if x is None:
        return "–"
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def variation(v):
    if v is None or v == "":
        return '<span class="var">–</span>'
    try:
        v = float(v)
    except (TypeError, ValueError):
        return f'<span class="var">{e(v)}</span>'
    classe = "hausse" if v > 0 else "baisse" if v < 0 else ""
    signe = "+" if v > 0 else ""
    return f'<span class="var {classe}">{signe}{nombre(v, 2)} %</span>'


def courbe(points, largeur=110, hauteur=28):
    pts = [p for p in points if p is not None]
    if len(pts) < 2:
        return ""
    mn, mx = min(pts), max(pts)
    et = (mx - mn) or 1
    coords = " ".join(f"{i * largeur / (len(pts) - 1):.1f},{hauteur - 2 - (p - mn) / et * (hauteur - 4):.1f}"
                      for i, p in enumerate(pts))
    classe = "hausse" if pts[-1] >= pts[0] else "baisse"
    return (f'<svg class="courbe {classe}" viewBox="0 0 {largeur} {hauteur}" width="{largeur}" '
            f'height="{hauteur}" aria-hidden="true"><polyline points="{coords}"/></svg>')


def graphe_heures(heures):
    """Température (ligne) et probabilité de pluie (barres) sur 24 h."""
    if not heures:
        return ""
    L, H, m = 320, 90, 14
    temps = [h["temp"] for h in heures]
    mn, mx = min(temps), max(temps)
    et = (mx - mn) or 1
    pas = L / len(heures)
    barres = "".join(
        f'<rect x="{i * pas + 1:.1f}" y="{H - m - (h["proba_pluie"] or 0) / 100 * (H - 2 * m):.1f}" '
        f'width="{pas - 2:.1f}" height="{(h["proba_pluie"] or 0) / 100 * (H - 2 * m):.1f}" class="pluie"/>'
        for i, h in enumerate(heures))
    ligne = " ".join(f"{i * pas + pas / 2:.1f},{H - m - (t - mn) / et * (H - 2 * m):.1f}"
                     for i, t in enumerate(temps))
    reperes = "".join(f'<text x="{i * pas + pas / 2:.1f}" y="{H - 2}" class="axe">{heures[i]["h"][:2]}h</text>'
                      for i in range(0, len(heures), 6))
    imx, imn = temps.index(mx), temps.index(mn)
    etiq = (f'<text x="{imx * pas + pas / 2:.1f}" y="{m - 3}" class="etiq">{nombre(mx, 0)}°</text>'
            f'<text x="{imn * pas + pas / 2:.1f}" y="{H - m + 11}" class="etiq">{nombre(mn, 0)}°</text>')
    return (f'<svg class="heures" viewBox="0 0 {L} {H}" role="img" '
            f'aria-label="Température et probabilité de pluie heure par heure">'
            f'{barres}<polyline class="temp" points="{ligne}"/>{etiq}{reperes}</svg>')


def carte_ville_compacte(m):
    """Une ligne par ville : ciel, températures et pluie du jour, tendance du lendemain."""
    j, d = m["jours"][0], (m["jours"][1:2] or [{}])[0]
    ico, txt = CODES_METEO.get(j.get("weather_code"), ("❔", "Inconnu"))
    ico2 = CODES_METEO.get(d.get("weather_code"), ("", ""))[0]
    return (f'<div class="tuile"><div class="ville">{e(m["ville"])}</div><div class="ico-grand">{ico}</div>'
            f'<div class="ciel">{e(txt)}</div>'
            f'<div class="t"><b>{nombre(j.get("temperature_2m_max"), 0)}°</b> {nombre(j.get("temperature_2m_min"), 0)}°</div>'
            f'<div class="pluie">💧 {nombre(j.get("precipitation_sum"), 0)} mm</div>'
            f'<div class="demain">demain {ico2} {nombre(d.get("precipitation_sum"), 0)} mm</div></div>')


def carte_ville(m):
    jours = m["jours"]
    blocs = []
    for i, j in enumerate(jours[:2]):
        ico, txt = CODES_METEO.get(j.get("weather_code"), ("❔", "Inconnu"))
        blocs.append(f"""
        <div class="jour">
          <div class="jour-nom">{"Aujourd'hui" if i == 0 else "Demain"}</div>
          <div class="ico">{ico}</div>
          <div class="ciel">{e(txt)}</div>
          <div class="temps"><b>{nombre(j.get("temperature_2m_max"), 0)}°</b> / {nombre(j.get("temperature_2m_min"), 0)}°</div>
          <div class="detail">💧 {nombre(j.get("precipitation_sum"), 1)} mm · {e(j.get("precipitation_probability_max"))} %</div>
          <div class="detail">💨 {nombre(j.get("wind_speed_10m_max"), 0)} km/h · rafales {nombre(j.get("wind_gusts_10m_max"), 0)}</div>
        </div>""")
    lever = (jours[0].get("sunrise") or "")[11:16]
    coucher = (jours[0].get("sunset") or "")[11:16]
    return f"""
    <div class="carte ville">
      <h3>{e(m["ville"])} <span class="discret">{e(m["dept"])}</span></h3>
      <div class="jours">{"".join(blocs)}</div>
      {graphe_heures(m.get("heures"))}
      <div class="discret petit">Barres : risque de pluie · ligne : température · 🌅 {e(lever)} – 🌇 {e(coucher)}</div>
    </div>"""


def bloc_sources(sources):
    if not sources:
        return ""
    parts = []
    for s in sources:
        if isinstance(s, dict):
            t = s.get("nom") or "source"
            if s.get("date"):
                t += f" ({s['date']})"
            parts.append(lien(s.get("url"), t))
        else:
            parts.append(lien(s, "source"))
    return '<div class="sources">Sources : ' + " · ".join(parts) + "</div>"


FIABILITE = {"confirme": ("✔ confirmé", "ok"), "une_source": ("◐ une seule source", "moyen"),
             "analyse": ("✎ analyse", "analyse")}


def lien_approfondir(date_iso, cle, n):
    """Lien pointdumatin:// traité par approfondir.py : l'analyse tourne en ligne de commande dans
    ~/claude puis s'ouvre dans l'app. Le lien ne porte qu'une référence (date, rubrique, rang) ;
    le texte de la demande est reconstruit en local à partir de la rédaction archivée."""
    if PUBLIC:  # le lien ne fonctionne que sur cet ordinateur
        return ""
    ref = {"date": date_iso, "section": cle, "n": n}
    if P["sous_dossier"]:
        ref["profil"] = P["sous_dossier"]
    params = urllib.parse.urlencode(ref)
    return (f'<a class="approfondir" href="pointdumatin://approfondir?{e(params)}" '
            f'title="Analyse approfondie en arrière-plan (3 à 5 min), puis ouverture dans Claude">'
            f'🔎 Approfondir avec Claude</a>')


DOMAINES = {"mines": "⛏️ mines", "finance": "💶 finance", "politique": "🏛️ politique",
            "entreprises": "🏢 entreprises"}


def article(it, lien_html="", replie=False):
    fia = FIABILITE.get(it.get("fiabilite"))
    badge = f'<span class="badge {fia[1]}">{fia[0]}</span>' if fia else ""
    if it.get("statut"):
        badge = f'<span class="badge statut">{e(it["statut"])}</span> ' + badge
    if it.get("domaine") in DOMAINES:
        badge = f'<span class="badge domaine">{DOMAINES[it["domaine"]]}</span> ' + badge
    if it.get("inondation_majeure") is True:
        badge = '<span class="badge inondation">🌊 inondation majeure</span> ' + badge
    urgent = " urgent" if it.get("importance") == "haute" or it.get("inondation_majeure") is True else ""
    pourquoi = f'<p class="pourquoi"><b>Pourquoi c\'est important :</b> {e(it["pourquoi"])}</p>' if it.get("pourquoi") else ""
    impact = (f'<p class="impact"><b>💰 Impact économique :</b> {e(it["impact_economique"])}</p>'
              if it.get("impact_economique") else "")
    reference = f'<p class="discret petit">Texte : {e(it["reference"])}</p>' if it.get("reference") else ""
    corps = f"""
        <p>{e(it.get("texte"))}</p>
        {reference}
        {impact}
        {pourquoi}
        <div class="pied-item">{bloc_sources(it.get("sources"))}{lien_html}</div>"""
    if replie:
        return f"""
      <details class="item{urgent}">
        <summary><h4>{e(it.get("titre"))} {badge}</h4></summary>{corps}
      </details>"""
    return f"""
      <article class="item{urgent}">
        <h4>{e(it.get("titre"))} {badge}</h4>{corps}
      </article>"""


CHIFFRES = {"or": "📈 Cours de l'or", "economie": "📊 Cours, matières premières et leone",
            "expatries": "🛂 Conseils officiels aux voyageurs", "monde": "🌋 Alertes catastrophes GDACS",
            "finance": "📊 Marchés, devises et cryptos", "catastrophes": "🌋 Séismes et alertes GDACS"}


def ligne_cours_or(marches):
    for c in marches or []:
        if c["nom"].lower().startswith("or"):
            return (f'<p class="commentaire">Once d\'or : <b>{e(c["valeur"])}</b> {variation(c.get("variation_pct"))} '
                    f'<span class="discret petit">(clôture du {e(c["date"])}, Yahoo Finance)</span></p>')
    return ""


def bloc_conseils(conseils):
    if not conseils:
        return ""
    lignes = "".join(f"<tr><td class='num'>{e(c['date'][8:10] + '/' + c['date'][5:7] + '/' + c['date'][:4])}</td>"
                     f"<td>{lien(c.get('url'), c['source'])}</td><td>{e(c.get('texte'))}</td></tr>" for c in conseils)
    return (f'<div class="carte"><h3>Conseils officiels aux voyageurs : dernières mises à jour</h3>'
            f'<table><tbody>{lignes}</tbody></table><div class="discret petit">Voir aussi '
            f'{lien("https://www.diplomatie.gouv.fr/fr/information-par-pays/sierra-leone/conseils-aux-voyageurs-securite", "France Diplomatie")} · '
            f'{lien("https://diplomatie.belgium.be/fr/pays/sierra-leone/voyager-en-sierra-leone-conseils-aux-voyageurs/derniere-mise-jour-en-sierra-leone", "Belgique")}'
            f'</div></div>')


def table_marches(lignes, titre):
    if not lignes:
        return ""
    rangs = "".join(f"<tr><td>{e(l.get('nom'))}</td><td class='num'>{e(l.get('valeur'))}</td>"
                    f"<td class='num'>{variation(l.get('variation_pct'))}</td></tr>" for l in lignes)
    return (f'<div class="carte"><h3>{e(titre)}</h3><table><thead><tr><th>Nom</th><th class="num">Valeur</th>'
            f'<th class="num">Variation</th></tr></thead><tbody>{rangs}</tbody></table></div>')


def table_cryptos(cryptos):
    if not cryptos:
        return '<div class="carte"><h3>Cryptomonnaies</h3><p class="discret">Données indisponibles.</p></div>'
    rangs = "".join(
        f"<tr><td><b>{e(c['symbole'])}</b> <span class='discret'>{e(c['nom'])}</span></td>"
        f"<td class='num'>{nombre(c['prix'], 2 if (c['prix'] or 0) < 100 else 0)} €</td>"
        f"<td class='num'>{variation(c.get('var_24h'))}</td><td class='num'>{variation(c.get('var_7j'))}</td>"
        f"<td class='masque-mobile'>{courbe(c.get('courbe_7j', []))}</td></tr>" for c in cryptos)
    return (f'<div class="carte"><h3>Cryptomonnaies — top 10</h3><table><thead><tr><th>Crypto</th>'
            f'<th class="num">Prix</th><th class="num">24 h</th><th class="num">7 j</th>'
            f'<th class="masque-mobile">7 jours</th></tr></thead><tbody>{rangs}</tbody></table>'
            f'<div class="discret petit">Source : {lien("https://www.coingecko.com", "CoinGecko")}</div></div>')


def table_devises(dev):
    if not dev:
        return ""
    noms = {"USD": "Dollar US", "GBP": "Livre sterling", "CHF": "Franc suisse", "JPY": "Yen", "EUR": "Euro",
            "GNF": "Franc guinéen", "LRD": "Dollar libérien", "XOF": "Franc CFA (BCEAO)"}
    if dev.get("base") == "SLE":
        rangs = "".join(f"<tr><td>1 {e(noms.get(k, k))}</td><td class='num'>{nombre(v, 4 if v < 1 else 2)} leones</td></tr>"
                        for k, v in dev["taux"].items())
        return (f'<div class="carte"><h3>Le leone (SLE)</h3><table><tbody>{rangs}</tbody></table>'
                f'<div class="discret petit">Taux officiel indicatif du {e(dev["date"])} · '
                f'{lien("https://open.er-api.com", "open.er-api.com")} ; le marché parallèle peut s\'en écarter</div></div>')
    rangs = "".join(f"<tr><td>1 € en {e(noms.get(k, k))}</td><td class='num'>{nombre(v, 4 if v < 10 else 2)}</td></tr>"
                    for k, v in dev["taux"].items())
    return (f'<div class="carte"><h3>Devises</h3><table><tbody>{rangs}</tbody></table>'
            f'<div class="discret petit">Taux de référence BCE du {e(dev["date"])} · '
            f'{lien("https://frankfurter.dev", "Frankfurter")}</div></div>')


def bloc_seismes(seismes):
    if not seismes:
        return '<p class="discret">Aucun séisme de magnitude 5 ou plus dans les dernières 24 h (USGS).</p>'
    rangs = "".join(
        f"<tr><td class='num'><b>{nombre(s['magnitude'], 1)}</b></td><td>{lien(s['url'], s['lieu'])}"
        f"{' 🌊 tsunami possible' if s['tsunami'] else ''}</td><td class='num'>{e(s['heure'])}</td></tr>"
        for s in seismes)
    return (f'<div class="carte"><h3>Séismes ≥ 5 (24 h)</h3><table><thead><tr><th class="num">Mag.</th>'
            f'<th>Lieu</th><th class="num">Heure</th></tr></thead><tbody>{rangs}</tbody></table>'
            f'<div class="discret petit">Source : {lien("https://earthquake.usgs.gov", "USGS")}</div></div>')


def bloc_gdacs(alertes):
    if not alertes:
        return ""
    rangs = "".join(
        f"<tr><td><span class='vigilance {NIVEAUX.get(a['niveau'], '')}'>{e(a['niveau'])}</span></td>"
        f"<td>{e(a['type'])}</td><td>{lien(a.get('url'), a.get('nom'))}<br><span class='discret petit'>"
        f"{e(a.get('pays'))}{' · ' + e(a['gravite']) if a.get('gravite') else ''}</span></td>"
        f"<td class='num'>{e(a['debut'][8:10] + '/' + a['debut'][5:7])} → "
        f"{'en cours' if a.get('en_cours') else e(a['fin'][8:10] + '/' + a['fin'][5:7])}</td></tr>"
        for a in alertes[:12])
    return (f'<div class="carte"><h3>Alertes GDACS orange et rouges</h3><table><thead><tr><th>Niveau</th>'
            f'<th>Type</th><th>Événement</th><th class="num">Période</th></tr></thead><tbody>{rangs}</tbody></table>'
            f'<div class="discret petit">Source : {lien("https://www.gdacs.org", "GDACS")} '
            f'(système mondial d\'alerte aux catastrophes)</div></div>')


NIVEAUX = {"vert": "vert", "jaune": "jaune", "orange": "orange", "rouge": "rouge"}


def bloc_vigilances(vig, auto=None):
    """Vigilances de la rédaction, sinon celles de MeteoAlarm ; auto == [] : aucune vigilance en cours."""
    vig = vig or auto
    if not vig:
        if auto == []:
            depts = ", ".join(v["dept"].split(" (")[0] for v in VILLES)
            return (f'<div class="vigilances">⚠️ Vigilance Météo-France : <span class="vigilance vert">'
                    f'{e(depts)} : aucune vigilance en cours</span> <span class="discret petit">(MeteoAlarm)</span></div>')
        return ""
    puces = "".join(
        f'<span class="vigilance {NIVEAUX.get(str(v.get("niveau", "")).lower(), "")}">'
        f'{e(v.get("departement"))} : {e(v.get("niveau"))}'
        f'{" — " + e(v["phenomene"]) if v.get("phenomene") else ""}</span>' for v in vig)
    return f'<div class="vigilances">⚠️ Vigilance Météo-France : {puces}</div>'


CSS = """
:root{--fond:#f2f3f5;--carte:#fff;--texte:#111317;--doux:#5b6170;--trait:#e3e5ea;--accent:#e0301e;
--accent-doux:#fde8e5;--encre:#111317;--hausse:#0f8a4f;--baisse:#d1281b;--pluie:#5b9be6;--temp:#f08a24;
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
@media (prefers-color-scheme:dark){:root{--fond:#0d0f12;--carte:#171a1f;--texte:#f1f2f4;--doux:#a3a9b6;--trait:#2a2e36;
--accent:#ff5a46;--accent-doux:#3a1714;--encre:#f1f2f4;--hausse:#3fd08a;--baisse:#ff6b5e;--pluie:#4d84c9;--temp:#f6a14a}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--fond);color:var(--texte);font:16px/1.6 var(--sans);-webkit-text-size-adjust:100%;-webkit-font-smoothing:antialiased}
main{max-width:860px;margin:0 auto;padding:0 16px 64px}
a{color:inherit;text-decoration-color:var(--accent);text-underline-offset:3px}
.une{padding:28px 0 16px}
.surtitre{font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--doux)}
.direct{color:var(--accent);font-size:.7rem;vertical-align:1px}
.une h1{font-weight:850;font-size:clamp(2rem,7vw,3.1rem);line-height:1.02;letter-spacing:-.035em;margin:6px 0 8px}
.meta{margin:0;color:var(--doux);font-size:.84rem}
.langues{margin:12px 0 0;font-size:.88rem;font-weight:600}
.langues a{display:inline-block;padding:4px 12px;border-radius:6px;background:var(--encre);color:var(--fond);text-decoration:none}
.bref{background:var(--carte);border-radius:14px;padding:6px 20px;margin:4px 0 6px}
.bref h2{all:unset;display:inline-block;margin:14px 0 2px;font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#fff;background:var(--accent);padding:3px 8px;border-radius:4px}
.bref ol{list-style:none;margin:0;padding:0;counter-reset:n}
.bref li{counter-increment:n;display:flex;gap:14px;align-items:baseline;padding:12px 0;border-top:1px solid var(--trait);font-weight:650;line-height:1.35;letter-spacing:-.005em}
.bref li:first-child{border-top:none;font-size:1.4rem;font-weight:800;letter-spacing:-.02em;line-height:1.2;padding-top:10px}
.bref li::before{content:counter(n);font-weight:800;color:var(--accent);min-width:1em;font-variant-numeric:tabular-nums}
.bref li:first-child::before{content:none}
.sommaire{position:sticky;top:0;z-index:5;display:flex;gap:6px;overflow-x:auto;margin:0 -16px;padding:10px 16px;
background:color-mix(in srgb,var(--fond) 90%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);scrollbar-width:none;border-bottom:1px solid var(--trait)}
.sommaire::-webkit-scrollbar{display:none}
.sommaire a{flex:none;font-size:.82rem;font-weight:650;text-decoration:none;color:var(--texte);background:var(--carte);border:1px solid var(--trait);border-radius:99px;padding:6px 13px;white-space:nowrap}
.sommaire a:hover,.sommaire a:active{background:var(--encre);color:var(--fond);border-color:var(--encre)}
h2{font-size:1.5rem;font-weight:850;letter-spacing:-.025em;line-height:1.15;margin:36px 0 12px;display:flex;align-items:center;gap:10px;scroll-margin-top:64px}
h2::before{content:"";width:5px;align-self:stretch;border-radius:3px;background:var(--accent);flex:none}
.pastille{font-size:1.15rem;line-height:1}
h3{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--doux);margin:0 0 10px;font-weight:800}
h4{font-size:1.06rem;font-weight:750;margin:0 0 6px;line-height:1.3;letter-spacing:-.01em}
.discret{color:var(--doux)} .petit{font-size:.82rem;margin-top:8px}
.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.carte{background:var(--carte);border-radius:14px;padding:16px 18px;overflow-x:auto}
.jours{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}
.jour{text-align:center} .jour-nom{font-weight:700;font-size:.8rem;color:var(--doux);text-transform:uppercase;letter-spacing:.05em}
.ico{font-size:2rem;line-height:1.2} .ciel{font-size:.85rem;color:var(--doux)}
.temps{font-size:1.2rem} .detail{font-size:.8rem;color:var(--doux)}
svg.heures{width:100%;height:auto;display:block}
svg.heures .pluie{fill:var(--pluie);opacity:.7}
svg.heures .temp{fill:none;stroke:var(--temp);stroke-width:2.2}
svg.heures .axe,svg.heures .etiq{font-size:9px;fill:var(--doux);text-anchor:middle}
svg.heures .etiq{fill:var(--texte);font-weight:700}
svg.courbe polyline{fill:none;stroke-width:1.6}
svg.courbe.hausse polyline{stroke:var(--hausse)} svg.courbe.baisse polyline{stroke:var(--baisse)}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th{text-align:left;color:var(--doux);font-weight:800;font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;border-bottom:2px solid var(--encre);padding:6px}
td{padding:8px 6px;border-bottom:1px solid var(--trait);vertical-align:middle}
tr:last-child td{border-bottom:none}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.var.hausse{color:var(--hausse);font-weight:700} .var.baisse{color:var(--baisse);font-weight:700}
.liste{background:var(--carte);border-radius:14px;overflow:hidden}
.item{background:var(--carte);padding:16px 18px;border-top:1px solid var(--trait)}
.liste>.item:first-child{border-top:none}
.item.urgent>h4::before,.item.urgent>summary h4::before{content:"À la une";display:inline-block;font-size:.62rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin-right:8px;vertical-align:2px}
.item p{margin:8px 0}
.pourquoi{font-size:.92rem}
.sources{font-size:.78rem;color:var(--doux)}
.sources a{color:var(--doux)}
.pied-item{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin-top:10px}
.approfondir{font-size:.78rem;font-weight:700;text-decoration:none;padding:5px 12px;border-radius:6px;background:var(--encre);color:var(--fond);white-space:nowrap}
.approfondir:hover{background:var(--accent)}
.impact{font-size:.9rem;background:var(--fond);border-radius:8px;padding:8px 12px;border-left:3px solid var(--temp)}
.badge{display:inline-block;font-size:.64rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;padding:2px 6px;border-radius:4px;border:1px solid var(--trait);color:var(--doux);vertical-align:middle;white-space:nowrap;margin-left:4px}
.badge.ok{color:var(--hausse);border-color:color-mix(in srgb,var(--hausse) 40%,transparent)}
.badge.moyen{color:#a86b00;border-color:#e7c27a}
.badge.analyse{color:#5b4bd1;border-color:#c5bdf3}
.badge.domaine{color:#fff;background:var(--accent);border-color:var(--accent)}
.badge.statut{color:var(--texte);border-color:var(--texte)}
.badge.inondation{color:#fff;background:#1f6fd1;border-color:#1f6fd1}
@media (prefers-color-scheme:dark){.badge.moyen{color:#f0c060;border-color:#6b5420}.badge.analyse{color:#b3a8ff;border-color:#463d80}}
.vigilances{margin:4px 0 14px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.vigilance{padding:3px 12px;border-radius:6px;font-size:.84rem;font-weight:650}
.vigilance.jaune{background:#ffe866;color:#4a3d00}.vigilance.orange{background:#ffb066;color:#4d2400}
.vigilance.rouge{background:#ff7a70;color:#4a0000}.vigilance.vert{background:#c9f0d6;color:#124a26}
.commentaire{margin:10px 0 14px;font-size:.98rem}
.consigne{margin:-4px 0 10px}
.agenda td:first-child{white-space:nowrap;font-weight:800;width:1%;color:var(--accent)}
details.item{padding:0}
details.item summary{cursor:pointer;list-style:none;display:flex;gap:12px;align-items:flex-start;padding:15px 18px}
details.item summary::-webkit-details-marker{display:none}
details.item summary::after{content:"+";margin-left:auto;flex:none;font-weight:400;font-size:1.5rem;line-height:1;color:var(--doux);transition:transform .2s}
details.item[open] summary::after{transform:rotate(45deg);color:var(--accent)}
details.item summary h4{margin:0}
details.item>:not(summary){margin-left:18px;margin-right:18px}
details.item>.pied-item{margin-bottom:16px}
details.item .carte{border:1px solid var(--trait)}
details.item>.tendance{margin-bottom:16px}
#meteo{border-radius:14px;margin-bottom:6px}
.meteo-compacte{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:12px}
.tuile{background:var(--fond);border-radius:12px;padding:12px;text-align:center}
.tuile .ville{font-weight:800;font-size:.9rem}
.ico-grand{font-size:1.9rem;line-height:1.3}
.tuile .ciel{font-size:.78rem}
.tuile .t{font-size:1.05rem} .tuile .t b{font-size:1.3rem;font-weight:800}
.tuile .pluie{font-size:.85rem;font-weight:650}
.tuile .demain{font-size:.75rem;color:var(--doux);margin-top:2px}
.tendance td,.tendance th{text-align:center;padding:5px 2px;font-size:.84rem}
.tendance td:first-child,.tendance th:first-child{text-align:left}
footer{margin-top:48px;padding-top:16px;border-top:2px solid var(--encre);font-size:.8rem;color:var(--doux)}
@media (max-width:600px){
/* téléphone, souvent lu dehors : texte plus grand, contraste renforcé, cibles tactiles larges */
:root{--doux:#3f4450;--trait:#d5d8df}
body{font-size:17.5px;line-height:1.6}
.masque-mobile{display:none} h2{font-size:1.4rem;margin-top:30px}
.bref{padding:4px 16px} .bref li{font-size:1.03rem} .bref li:first-child{font-size:1.32rem}
.item{padding:15px 14px} .item p{font-size:1.02rem}
h4{font-size:1.12rem}
details.item summary{padding:15px 14px;min-height:50px} details.item>:not(summary){margin-left:14px;margin-right:14px}
.sommaire a{font-size:.9rem;padding:8px 14px}
.meteo-compacte{grid-template-columns:1fr 1fr}
.sources,.petit,.meta{font-size:.86rem}
table{font-size:.95rem}}
@media (max-width:600px) and (prefers-color-scheme:dark){:root{--doux:#c3c8d2;--trait:#353a44}}
@media (prefers-contrast:more){:root{--doux:#30343d;--trait:#b8bcc6}}
"""


def bloc_rappels(dus, traites):
    if not dus and not traites:
        return ""
    par_id = {str(t.get("id")): t for t in traites if isinstance(t, dict)}
    lignes = []
    vus = set()
    for r in dus + [t for t in traites if str(t.get("id")) not in {str(x.get("id")) for x in dus}]:
        rid = str(r.get("id"))
        if rid in vus:
            continue
        vus.add(rid)
        t = par_id.get(rid, {})
        etat = {"regle": '<span class="badge ok">✔ réglé, retiré des rappels</span>',
                "en_attente": '<span class="badge moyen">⏳ à revoir demain</span>'}.get(
                    t.get("statut"), '<span class="badge moyen">non traité</span>')
        lignes.append(f"""
      <article class="item">
        <h4>{e(r.get("texte") or rid)} {etat}</h4>
        {f'<p>{e(t["reponse"])}</p>' if t.get("reponse") else ""}
        {bloc_sources(t.get("sources"))}
        <div class="discret petit">Rappel « {e(rid)} »{" prévu le " + e(r["date"]) if r.get("date") else ""}</div>
      </article>""")
    return '<h2 id="rappels"><span class="pastille">🔔</span>Rappels du jour</h2>' + "".join(lignes)


def tendance_semaine(villes):
    """Tableau ville par jour : ciel et pluie prévue sur toute la période collectée."""
    jours = villes[0]["jours"]
    if len(jours) < 3:
        return ""
    tete = "".join(f"<th>{JOURS[dt.date.fromisoformat(j['time']).weekday()][:3]} "
                   f"{dt.date.fromisoformat(j['time']).day}</th>" for j in jours)
    lignes = "".join(
        f"<tr><td><b>{e(m['ville'])}</b></td>" + "".join(
            f"<td>{CODES_METEO.get(j.get('weather_code'), ('❔', ''))[0]}<br>"
            f"<span class='petit'>{nombre(j.get('precipitation_sum'), 0)} mm</span></td>" for j in m["jours"])
        + "</tr>" for m in villes)
    return (f'<div class="carte tendance"><h3>Tendance sur {len(jours)} jours</h3><table><thead><tr><th></th>{tete}'
            f'</tr></thead><tbody>{lignes}</tbody></table></div>')


def meteo_html(villes):
    if not villes:
        return '<p class="discret">Météo indisponible.</p>'
    if P["meteo_compacte"]:
        return ('<div class="carte meteo-compacte">' + "".join(carte_ville_compacte(m) for m in villes) + "</div>"
                + tendance_semaine(villes))
    return '<div class="grille">' + "".join(carte_ville(m) for m in villes) + "</div>"


COURTS = {"rappels": "🔔 Rappels", "meteo": "🌦️ Météo", "finance": "💶 Finance", "catastrophes": "🌋 Catastrophes",
          "geopolitique": "🌍 Géopolitique", "tech_ia": "🤖 Tech & IA", "sciences_sante": "🔬 Sciences",
          "or": "🥇 Or", "sierra_leone": "🇸🇱 Politique", "lois": "🏛️ Lois & mines", "economie": "💰 Économie",
          "societe": "👥 Société", "expatries": "🧳 Expatriés", "voisins": "🧭 Voisins", "monde": "🌐 Monde",
          "agenda": "📅 Agenda"}
COURTS_EN = {"rappels": "🔔 Reminders", "meteo": "🌦️ Weather", "or": "🥇 Gold", "sierra_leone": "🇸🇱 Politics",
             "lois": "🏛️ Laws & mining", "economie": "💰 Economy", "societe": "👥 Society",
             "expatries": "🧳 Expats", "voisins": "🧭 Neighbours", "monde": "🌐 World", "agenda": "📅 Agenda"}


def sommaire(sections, rappels=False):
    """Barre de rubriques collée en haut de l'écran, pour sauter d'une rubrique à l'autre."""
    cles = (["rappels"] if rappels else []) + ["meteo"] + [c for c, _, _ in SECTIONS] + ["agenda"]
    return ('<nav class="sommaire">' + "".join(f'<a href="#{c}">{COURTS.get(c, c)}</a>' for c in cles)
            + "</nav>")


def bloc_meteo(meteo, d):
    contenu = (bloc_vigilances(meteo.get("vigilances"), d.get("vigilances"))
               + (f'<p class="commentaire">{e(meteo["commentaire"])}</p>' if meteo.get("commentaire") else "")
               + meteo_html(d["meteo"])
               + f'<p class="discret petit">Prévisions : {lien("https://open-meteo.com", "Open-Meteo")}</p>')
    if not P["meteo_compacte"]:
        return '<h2 id="meteo"><span class="pastille">🌦️</span>Météo</h2>' + contenu
    resume = str(meteo.get("commentaire") or "").split(". ")[0].split(" : ")[0].rstrip(".")
    if len(resume) > 70:
        resume = resume[:67].rsplit(" ", 1)[0] + "…"
    return (f'<details class="item" id="meteo"><summary><h4>🌦️ Météo{" : " + e(resume) if resume else ""}</h4></summary>'
            f'{contenu}</details>')


JOURS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]
METEO_EN = {"Ciel clair": "Clear sky", "Plutôt dégagé": "Mostly clear", "Partiellement nuageux": "Partly cloudy",
            "Couvert": "Overcast", "Brouillard": "Fog", "Brouillard givrant": "Freezing fog",
            "Bruine légère": "Light drizzle", "Bruine": "Drizzle", "Bruine forte": "Heavy drizzle",
            "Pluie faible": "Light rain", "Pluie": "Rain", "Pluie forte": "Heavy rain",
            "Averses faibles": "Light showers", "Averses": "Showers", "Averses violentes": "Violent showers",
            "Orages": "Thunderstorms", "Orages avec grêle": "Thunderstorms with hail",
            "Orages violents avec grêle": "Severe thunderstorms with hail", "Inconnu": "Unknown"}
# Textes fixes de la page (la rédaction anglaise fournit le contenu) ; du plus long au plus court
INTERFACE_EN = [
    ("Point du matin — Sierra Leone", "Morning brief — Sierra Leone"),
    ("Or : mines, prix, exportations", "Gold: mining, prices, exports"),
    ("Sierra Leone : politique, justice, institutions", "Sierra Leone: politics, justice, institutions"),
    ("Lois, Journal officiel et mines", "Laws, Official Gazette and mining"),
    ("Économie, prix et ressources", "Economy, prices and resources"),
    ("Société, santé, éducation, vie locale", "Society, health, education, local life"),
    ("Expatriés : sécurité et vie pratique", "Expatriates: safety and practical life"),
    ("Pays voisins et région", "Neighbouring countries and region"),
    ("Le monde en bref", "The world in brief"),
    ("Cliquez sur un titre pour lire le détail.", "Tap a headline to read more."),
    ("chiffres collectés à", "figures collected at"), ("rédigé à", "written at"),
    ("(heure de Freetown)", "(Freetown time)"),
    ('content:"À la une"', 'content:"Top story"'), ("🌦️ Météo : ", "🌦️ Weather: "), ("🌦️ Météo", "🌦️ Weather"), ("Tendance sur 7 jours", "7-day outlook"),
    ("<th>lun ", "<th>Mon "), ("<th>mar ", "<th>Tue "), ("<th>mer ", "<th>Wed "), ("<th>jeu ", "<th>Thu "),
    ("<th>ven ", "<th>Fri "), ("<th>sam ", "<th>Sat "), ("<th>dim ", "<th>Sun "), ("Prévisions :", "Forecast:"), (" · demain ", " · tomorrow "), ('<div class="demain">demain ', '<div class="demain">tomorrow '),
    ("✔ confirmé", "✔ confirmed"), ("◐ une seule source", "◐ single source"), ("✎ analyse", "✎ analysis"),
    ("⛏️ mines<", "⛏️ mining<"), ("🏛️ politique<", "🏛️ politics<"), ("🏢 entreprises<", "🏢 business<"),
    ("Pourquoi c'est important :", "Why it matters:"), ("💰 Impact économique :", "💰 Economic impact:"),
    (">Texte : ", ">Legal text: "), ("Sources : ", "Sources: "), ("Source : ", "Source: "),
    ("📈 Cours de l&#x27;or", "📈 Gold price"), ("📈 Cours de l'or", "📈 Gold price"), ("Once d&#x27;or :", "Gold, per ounce:"),
    ("Once d'or :", "Gold, per ounce:"), ("(clôture du ", "(close of "),
    ("📊 Cours, matières premières et leone", "📊 Commodities and the leone"),
    ("🛂 Conseils officiels aux voyageurs", "🛂 Official travel advice"),
    ("🌋 Alertes catastrophes GDACS", "🌋 GDACS disaster alerts"),
    ("Matières premières", "Commodities"), (">Nom<", ">Name<"), (">Valeur<", ">Value<"),
    (">Variation<", ">Change<"), ("Minerai de fer", "Iron ore"), ("Or (once)", "Gold (ounce)"),
    ("Riz (cwt)", "Rice (cwt)"), ("Cacao (t)", "Cocoa (t)"),
    ("Le leone (SLE)", "The leone (SLE)"), ("1 Dollar US", "1 US dollar"), ("1 Livre sterling", "1 Pound sterling"),
    ("1 Franc guinéen", "1 Guinean franc"), ("1 Dollar libérien", "1 Liberian dollar"),
    ("1 Franc CFA (BCEAO)", "1 CFA franc (BCEAO)"), ("Taux officiel indicatif du", "Indicative official rate of"),
    ("; le marché parallèle peut s&#x27;en écarter", "; the parallel market may differ"),
    ("; le marché parallèle peut s'en écarter", "; the parallel market may differ"),
    ("Conseils officiels aux voyageurs : dernières mises à jour", "Official travel advice: latest updates"),
    ("Royaume-Uni (FCDO)", "United Kingdom (FCDO)"), ("Ambassade des États-Unis", "US Embassy"),
    ("Voir aussi", "See also"), (">Belgique<", ">Belgium<"),
    ("Alertes GDACS orange et rouges", "GDACS orange and red alerts"), (">Niveau<", ">Level<"),
    (">Événement<", ">Event<"), (">Période<", ">Period<"), ("→ en cours", "→ ongoing"),
    (">rouge<", ">red<"), (">Séisme<", ">Earthquake<"), (">Cyclone<", ">Cyclone<"), (">Inondation<", ">Flood<"),
    (">Éruption<", ">Eruption<"), (">Sécheresse<", ">Drought<"), (">Feux de forêt<", ">Wildfires<"),
    ("(système mondial d&#x27;alerte aux catastrophes)", "(Global Disaster Alert and Coordination System)"),
    ("(système mondial d'alerte aux catastrophes)", "(Global Disaster Alert and Coordination System)"),
    ("📅 Cette semaine", "📅 This week"), ("</span>Cette semaine</h2>", "</span>This week</h2>"), ("Agenda non renseigné.", "No agenda today."),
    ("Rien de notable rédigé pour cette rubrique.", "Nothing notable today."),
    ("Source automatique en panne — ", "Automatic source unavailable — "),
    ("Informations seulement, aucun conseil financier.", "Information only, not financial advice."),
    ("Page générée par point-du-matin.py.", ""),
    ('<html lang="fr">', '<html lang="en">'),
]


def traduire_en(page, date_iso):
    """Version anglaise des textes fixes d'une page dont la rédaction est déjà en anglais."""
    date = dt.date.fromisoformat(date_iso)
    fr = f"{JOURS[date.weekday()]} {date.day} {MOIS[date.month - 1]} {date.year}"
    en = f"{JOURS_EN[date.weekday()]} {date.day} {MOIS_EN[date.month - 1]} {date.year}"
    page = page.replace(fr.capitalize(), en).replace(fr, en)
    for cle, libelle in COURTS_EN.items():
        page = page.replace(f'href="#{cle}">{COURTS[cle]}<', f'href="#{cle}">{libelle}<')
    page = page.replace("<h2>L'essentiel</h2>", "<h2>Top stories</h2>")
    for a, b in INTERFACE_EN:
        page = page.replace(a, b)
    for a, b in METEO_EN.items():
        page = page.replace(f">{a}<", f">{b}<")
    return page


def generer_html(d, red, dus=(), public=False, langue="fr"):
    global PUBLIC
    PUBLIC = public
    try:
        page = _generer_html(d, red, dus)
    finally:
        PUBLIC = False
    if public:
        autre, libelle = ("en.html", "English version") if langue == "fr" else ("index.html", "Version française")
        page = page.replace("<head>", '<head>\n<meta name="robots" content="noindex,nofollow">', 1)
        page = page.replace("</h1>", f'</h1>\n  <p class="langues"><a href="{autre}">{libelle}</a></p>', 1)
    return traduire_en(page, d["date"]) if langue == "en" else page


def _generer_html(d, red, dus=()):
    date = dt.date.fromisoformat(d["date"])
    titre_date = f"{JOURS[date.weekday()]} {date.day} {MOIS[date.month - 1]} {date.year}"
    meteo = red.get("meteo") or {}
    marches = red.get("marches") or {}
    sections = red.get("sections") or {}

    corps = [f"""
<header class="une">
  <div class="surtitre"><span class="direct">●</span> {e(titre_date.capitalize())}</div>
  <h1>{e(P["titre"])}</h1>
  <p class="meta">chiffres collectés à {e(d.get("collecte_a"))} · rédigé à {maintenant_local():%H:%M} (heure de {e(P["fuseau"].split("/")[1])})</p>
</header>
<section class="bref"><h2>L'essentiel</h2><ol>{"".join(f"<li>{e(t)}</li>" for t in red.get("en_bref", []))}</ol></section>
{sommaire(sections, bool(dus or red.get("rappels")))}
{bloc_rappels(list(dus), list(red.get("rappels") or []))}

{bloc_meteo(meteo, d)}
"""]

    for cle, ico, titre in SECTIONS:
        corps.append(f'<h2 id="{cle}"><span class="pastille">{ico}</span>{e(titre)}</h2>')
        blocs = P["blocs"].get(cle, ())
        replie = cle in P["replies"]
        corps_section, corps = corps, []  # les blocs automatiques sont repliés avec la rubrique
        if "cours_or" in blocs:
            corps.append(ligne_cours_or(d.get("marches")))
        if "marches" in blocs:
            if marches.get("commentaire"):
                corps.append(f'<p class="commentaire">{e(marches["commentaire"])}</p>')
            auto = d.get("marches") or []
            indices = marches.get("indices") or [c for c in auto if c["genre"] == "indice"]
            matieres = [c for c in auto if c["genre"] == "matiere"]
            noms_auto = {c["nom"].split(" ")[0].lower() for c in matieres}
            matieres += [m for m in marches.get("matieres") or []
                         if str(m.get("nom", "")).split(" ")[0].lower() not in noms_auto]
            corps.append('<div class="grille">'
                         + table_marches(indices, "Indices boursiers")
                         + table_marches(matieres, "Matières premières")
                         + (table_devises(d.get("devises")) if "devises" in blocs else "") + "</div><br>"
                         + (table_cryptos(d.get("cryptos")) + "<br>" if "cryptos" in blocs else ""))
        if "seismes" in blocs:
            corps.append(bloc_seismes(d.get("seismes")) + "<br>")
        if "gdacs" in blocs:
            corps.append(bloc_gdacs(d.get("gdacs")) + "<br>")
        if "conseils" in blocs:
            corps.append(bloc_conseils(d.get("conseils")) + "<br>")
        auto_html, corps = "".join(corps), corps_section
        if replie and (auto_html.strip() or sections.get(cle)):
            corps.append('<p class="discret petit consigne">Cliquez sur un titre pour lire le détail.</p>')
        if auto_html.strip():
            corps.append(f'<details class="item"><summary><h4>{CHIFFRES.get(cle, "📊 Chiffres du jour")}</h4></summary>'
                         f'{auto_html}</details>' if replie else auto_html)
        items = list(enumerate(sections.get(cle) or []))  # rang d'origine = référence du lien
        if cle == "catastrophes":  # inondations majeures en tête, puis importance haute
            items.sort(key=lambda p: (p[1].get("inondation_majeure") is not True,
                                      p[1].get("importance") != "haute"))
        if cle == "lois":  # mines et or en tête, puis importance haute
            items.sort(key=lambda p: (p[1].get("domaine") != "mines", p[1].get("importance") != "haute"))
        corps.append('<div class="liste">' + "".join(article(it, lien_approfondir(d["date"], cle, n), replie)
                                                     for n, it in items) + "</div>" if items
                     else '<p class="discret">Rien de notable rédigé pour cette rubrique.</p>')

    agenda = red.get("agenda") or []
    corps.append('<h2 id="agenda"><span class="pastille">📅</span>Cette semaine</h2>')
    corps.append('<div class="carte agenda"><table><tbody>'
                 + "".join(f"<tr><td>{e(a.get('date'))}</td><td>{e(a.get('evenement'))}</td></tr>" for a in agenda)
                 + "</tbody></table></div>" if agenda else '<p class="discret">Agenda non renseigné.</p>')

    notes = list(red.get("notes") or []) + [f"Source automatique en panne — {x}" for x in d.get("erreurs", [])]
    pied = "".join(f"<div>• {e(n)}</div>" for n in notes)
    corps.append(f'<footer>{pied}<div>Informations seulement, aucun conseil financier. '
                 f'Page générée par point-du-matin.py.</div></footer>')

    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(P["titre"].split(" ", 1)[1])} — {e(titre_date)}</title>
<style>{CSS}</style></head>
<body><main>{"".join(corps)}</main></body></html>
"""


# ---------------------------------------------------------------- publication

def notifier(titres, page):
    corps = "\n".join(t if t.startswith("🔔") else f"• {t}" for t in titres)
    try:
        subprocess.run(["notify-send", "--app-name=Point du matin", "--icon=weather-few-clouds",
                        "--expire-time=60000", P["titre"] + " : prêt", corps], timeout=10)
    except Exception as ex:
        print(f"Notification impossible : {ex}", file=sys.stderr)


def adresse_page(page):
    """URL du serveur local si actif (origine fixe : le navigateur retient l'autorisation des liens claude://),
    sinon chemin du fichier."""
    chemin = (P["sous_dossier"] + "/" if P["sous_dossier"] else "") + page.name
    try:
        urllib.request.urlopen(f"{SERVEUR_LOCAL}/{chemin}", timeout=2).close()
        return f"{SERVEUR_LOCAL}/{chemin}"
    except Exception:
        return str(page)


def ouvrir(page):
    try:
        subprocess.Popen(["xdg-open", adresse_page(page)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception as ex:
        print(f"Ouverture impossible : {ex}", file=sys.stderr)


def nettoyer():
    limite = dt.date.today() - dt.timedelta(days=ARCHIVE_JOURS)
    for f in list(DOSSIER.glob("*.html")) + list(DOSSIER.glob("donnees-*.json")) + list(DOSSIER.glob("redaction-*.json")) \
            + list(ETAT.glob("*.txt")):
        try:
            jour = dt.date.fromisoformat(f.stem.replace("donnees-", "").replace("redaction-", "")[:10])
        except ValueError:
            continue
        if jour < limite:
            f.unlink()


def publier(fichier, aujourdhui, ouvrir_page=True, notif=True):
    red = json.loads(Path(fichier).read_text())
    dus = rappels_dus(aujourdhui)
    pb = valider(red, dus)
    if pb:
        print("Rédaction invalide, corrige et relance :\n- " + "\n- ".join(pb), file=sys.stderr)
        sys.exit(2)
    cache = DOSSIER / f"donnees-{aujourdhui}.json"
    d = json.loads(cache.read_text()) if cache.exists() else collecte(aujourdhui)
    page_html = generer_html(d, red, dus)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    page = DOSSIER / f"{aujourdhui}.html"
    page.write_text(page_html)
    (DOSSIER / "index.html").write_text(page_html)
    # archive de la rédaction : approfondir.py y relit l'article désigné par un lien
    (DOSSIER / f"redaction-{aujourdhui}.json").write_text(json.dumps(red, ensure_ascii=False, indent=1))
    ETAT.mkdir(parents=True, exist_ok=True)
    titres = [t.strip()[:110] for t in red["en_bref"][:5]]
    lignes = [f"• {t}" for t in titres] + [f"🔔 {str(r.get('texte'))[:100]}" for r in dus]
    (ETAT / f"{aujourdhui}.txt").write_text("\n".join(lignes))
    clos = clore_rappels(red.get("rappels") or [], aujourdhui)
    if clos:
        print("Rappels marqués faits : " + ", ".join(clos))
    nettoyer()
    if notif:
        notifier(titres + [f"🔔 {str(r.get('texte'))[:100]}" for r in dus], page)
    if ouvrir_page:
        ouvrir(page)
    print(f"Page générée : {page}")


DEPOT_PUBLIC = Path(os.environ.get("POINT_DU_MATIN_DEPOT_PUBLIC", HOME / "claude/projets/keuzere.github.io"))


TEXTES_MDP = {
    "fr": {"titre": "Page privée", "instructions": "Point du matin Sierra Leone : saisissez le mot de passe.",
           "bouton": "OUVRIR", "erreur": "Mot de passe incorrect", "champ": "Mot de passe",
           "souvenir": "Se souvenir de moi sur cet appareil", "afficher": "Afficher", "masquer": "Masquer"},
    "en": {"titre": "Private page", "instructions": "Sierra Leone morning brief: enter the password.",
           "bouton": "OPEN", "erreur": "Wrong password", "champ": "Password",
           "souvenir": "Remember me on this device", "afficher": "Show", "masquer": "Hide"},
}


def mot_de_passe_public():
    """Variable POINT_DU_MATIN_MOT_DE_PASSE (routine cloud), sinon fichier privé du profil (portable)."""
    mdp = os.environ.get("POINT_DU_MATIN_MOT_DE_PASSE", "").strip()
    if not mdp:
        f = Path(os.path.expanduser(P["chiffrement"]["fichier_mdp"]))
        mdp = f.read_text().strip() if f.exists() else ""
    return mdp


def chiffrer(page, langue, mdp):
    """Chiffre une page HTML avec StatiCrypt (déchiffrée dans le navigateur avec le mot de passe)."""
    import tempfile
    t = TEXTES_MDP[langue]
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.html"
        src.write_text(page)
        r = subprocess.run(
            ["npx", "--yes", "staticrypt@3", str(src), "-d", str(Path(tmp) / "out"), "-c", "false",
             "--salt", P["chiffrement"]["sel"], "--remember", "0", "--short",
             "--template-title", t["titre"], "--template-instructions", t["instructions"],
             "--template-button", t["bouton"], "--template-error", t["erreur"],
             "--template-placeholder", t["champ"], "--template-remember", t["souvenir"],
             "--template-toggle-show", t["afficher"], "--template-toggle-hide", t["masquer"],
             "--template-color-primary", "#c4622d", "--template-color-secondary", "#f6f5f2"],
            env={**os.environ, "STATICRYPT_PASSWORD": mdp}, capture_output=True, text=True, timeout=300)
        sortie = Path(tmp) / "out" / "page.html"
        if r.returncode != 0 or not sortie.exists():
            sys.exit(f"Chiffrement impossible (StatiCrypt) : {(r.stderr or r.stdout).strip()[:300]}")
        return sortie.read_text()


def partager(fichier_fr, fichier_en, aujourdhui):
    """Publie la page du jour en français (index.html) et en anglais (en.html) sur le site GitHub Pages,
    sans liens locaux ni boutons « Approfondir », puis pousse le dépôt. Relançable : sans changement, rien n'est poussé."""
    if not P.get("public"):
        sys.exit("Ce profil n'a pas de page publique.")
    cache = DOSSIER / f"donnees-{aujourdhui}.json"
    d = json.loads(cache.read_text()) if cache.exists() else collecte(aujourdhui)
    # récupère d'abord ce qu'une autre machine (ou la routine cloud) a publié, pour pousser sans conflit
    subprocess.run(["git", "-C", str(DEPOT_PUBLIC), "pull", "--rebase", "-q"], capture_output=True)
    mdp = mot_de_passe_public() if P.get("chiffrement") else None
    if P.get("chiffrement") and not mdp:  # jamais de page en clair pour un profil protégé
        sys.exit("Mot de passe absent : définir POINT_DU_MATIN_MOT_DE_PASSE ou créer "
                 + P["chiffrement"]["fichier_mdp"] + ". Rien n'est publié.")
    cible = DEPOT_PUBLIC / P["public"]
    cible.mkdir(parents=True, exist_ok=True)
    for fichier, langue, nom in ((fichier_fr, "fr", "index.html"), (fichier_en, "en", "en.html")):
        red = json.loads(Path(fichier).read_text())
        pb = valider(red)
        if pb:
            print(f"Rédaction {langue} invalide, corrige et relance :\n- " + "\n- ".join(pb), file=sys.stderr)
            sys.exit(2)
        page = generer_html(d, red, public=True, langue=langue)
        (cible / nom).write_text(chiffrer(page, langue, mdp) if mdp else page)
    # copie du script dans le dépôt public : la routine cloud l'exécute depuis là, ordinateur éteint
    outil = DEPOT_PUBLIC / "outils" / Path(__file__).name
    if Path(__file__).resolve() != outil.resolve():
        outil.parent.mkdir(exist_ok=True)
        outil.write_bytes(Path(__file__).read_bytes())
    git = ["git", "-C", str(DEPOT_PUBLIC)]
    subprocess.run(git + ["add", P["public"], "outils"], check=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        print("Pages publiques déjà à jour.")
        return
    subprocess.run(git + ["commit", "-q", "-m", f"{P['titre'].split(' ', 1)[1]} du {aujourdhui}"], check=True)
    r = subprocess.run(git + ["push", "-q"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Envoi sur GitHub impossible : {r.stderr.strip()[:300]}")
    print(f"Pages publiées : https://keuzere.github.io/{P['public']}/ et en.html")


def main():
    args = sys.argv[1:]
    if "--profil" in args:
        i = args.index("--profil")
        nom = args[i + 1] if i + 1 < len(args) else ""
        if nom not in PROFILS:
            sys.exit(f"Profil inconnu : « {nom} ». Profils : " + ", ".join(PROFILS))
        appliquer_profil(nom)
        del args[i:i + 2]
    aujourdhui = dt.date.today()
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
    elif args[0] == "collecte":
        print(json.dumps(resume_pour_redaction(collecte(aujourdhui)), ensure_ascii=False, indent=1))
    elif args[0] == "rappels":
        print(json.dumps(rappels_dus(aujourdhui), ensure_ascii=False, indent=1))
    elif args[0] == "modele":
        print(json.dumps(modele(), ensure_ascii=False, indent=1))
    elif args[0] == "partager" and len(args) >= 3:
        partager(args[1], args[2], aujourdhui)
    elif args[0] == "publier" and len(args) >= 2:
        publier(args[1], aujourdhui, "--sans-ouvrir" not in args, "--sans-notif" not in args)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
