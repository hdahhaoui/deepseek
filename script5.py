import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
import re

# Configuration du scraping
SCRAPING_ENABLED = True  # Désactiver sur Streamlit Cloud si nécessaire
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
HEADERS = {'User-Agent': USER_AGENT}

def parse_power_value(val_str: str):
    """Convertit une chaîne contenant une puissance en valeur numérique (W)."""
    conversions = {
        'w': 1,
        'kw': 1000,
        'btu': 0.29307107
    }
    match = re.search(r'(\d+[\d.,]*)\s*(w|kw|btu)/?h?', val_str, re.IGNORECASE)
    if not match:
        return None
    
    value, unit = match.groups()
    try:
        return float(value.replace(',', '.')) * conversions[unit.lower()]
    except:
        return None

def find_energy_class(text: str):
    """Recherche la classe énergétique dans le texte."""
    class_match = re.search(r'(classe énergétique|energy class)[:\s]*([A-G][\+]*)', text, re.IGNORECASE)
    return class_match.group(2) if class_match else None

def extract_specs_from_text(text: str):
    """Extrait les spécifications techniques depuis un texte brut."""
    text = text.lower()
    specs = {
        'consumption_w': None,
        'cooling_w': None,
        'inverter': None,
        'energy_class': None
    }

    # Extraction de la consommation électrique
    consumption_match = re.search(
        r'(consommation|puissance absorbée|power consumption)[:\s]*([\d.,]+\s*(w|kw|btu))', 
        text, 
        re.IGNORECASE
    )
    if consumption_match:
        specs['consumption_w'] = parse_power_value(consumption_match.group(2))

    # Extraction de la puissance frigorifique
    cooling_match = re.search(
        r'(puissance frigorifique|cooling capacity|capacity)[:\s]*([\d.,]+\s*(w|kw|btu))', 
        text, 
        re.IGNORECASE
    )
    if cooling_match:
        specs['cooling_w'] = parse_power_value(cooling_match.group(2))

    # Détection de la technologie Inverter
    specs['inverter'] = 'Inverter' if 'inverter' in text else 'Non-Inverter'

    # Classe énergétique
    specs['energy_class'] = find_energy_class(text)

    return specs

def fetch_product_specs(model: str):
    """Tente de récupérer les spécifications via le web."""
    search_url = f"https://www.google.com/search?q={requests.utils.quote(model + ' technical specifications filetype:pdf')}"
    
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Recherche de liens PDF prioritaires
        pdf_links = [
            a['href'] for a in soup.find_all('a', href=True) 
            if 'pdf' in a['href'].lower() and 'google.com' not in a['href']
        ]
        
        # Téléchargement et analyse du premier PDF trouvé
        if pdf_links:
            pdf_url = parse_qs(urlparse(pdf_links[0]).get('q', [pdf_links[0]])[0]
            pdf_response = requests.get(pdf_url, headers=HEADERS, timeout=15)
            
            # Extraction de texte depuis le PDF
            from io import BytesIO
            from PyPDF2 import PdfReader
            with BytesIO(pdf_response.content) as data:
                reader = PdfReader(data)
                text = "\n".join([page.extract_text() for page in reader.pages])
            
            return extract_specs_from_text(text)

    except Exception as e:
        pass

    # Fallback sur le scraping HTML standard
    try:
        response = requests.get(f"https://www.google.com/search?q={requests.utils.quote(model)}", headers=HEADERS)
        soup = BeautifulSoup(response.text, 'html.parser')
        main_content = soup.find('div', id='search').get_text()
        return extract_specs_from_text(main_content)
    except:
        return None

# Interface Streamlit
st.title("🌀 Simulateur de consommation de climatiseur")
st.markdown("""
**Instructions :**
1. Entrez le modèle exact de votre climatiseur
2. Les spécifications techniques seront recherchées automatiquement
3. Complétez manuellement si nécessaire
""")

model_name = st.text_input("**Modèle du climatiseur** :", placeholder="Exemple : Daikin FTXS35K")

if SCRAPING_ENABLED:
    st.info("🔍 Le mode scraping web est activé")
else:
    st.warning("Le scraping web est désactivé - entrez les données manuellement")

# Section de saisie manuelle
with st.expander("🔧 Saisie manuelle des paramètres"):
    consumption = st.number_input("Consommation électrique (W) :", min_value=0.0, step=50.0)
    cooling_power = st.number_input("Puissance frigorifique (W) :", min_value=0.0, step=100.0)
    inverter = st.selectbox("Technologie Inverter :", ['Oui', 'Non'])
    energy_class = st.selectbox("Classe énergétique :", ['A+++', 'A++', 'A+', 'A', 'B', 'C', 'D', 'E', 'F', 'G'])

specs = None
if st.button("Rechercher automatiquement les spécifications"):
    if model_name:
        with st.spinner("Recherche des spécifications..."):
            specs = fetch_product_specs(model_name)
        
        if specs and specs['consumption_w'] and specs['cooling_w']:
            st.success("Données techniques trouvées !")
        else:
            st.warning("Certaines données n'ont pas pu être trouvées automatiquement")
            specs = None

# Calcul de la consommation
if specs or any([consumption, cooling_power]):
    st.subheader("Paramètres de calcul")
    
    # Fusion des données automatiques et manuelles
    final_consumption = specs['consumption_w'] if specs else consumption
    final_cooling = specs['cooling_w'] if specs else cooling_power
    
    # Affichage des spécifications
    col1, col2, col3 = st.columns(3)
    col1.metric("Consommation électrique", f"{final_consumption} W" if final_consumption else "N/A")
    col2.metric("Puissance frigorifique", f"{final_cooling} W" if final_cooling else "N/A")
    col3.metric("Efficacité énergétique", specs['energy_class'] if specs else energy_class)

    # Configuration d'utilisation
    st.markdown("---")
    usage_hours = st.slider("Heures d'utilisation quotidienne :", 0, 24, 8)
    days = st.number_input("Jours d'utilisation mensuelle :", 1, 31, 30)

    if final_consumption and usage_hours > 0:
        daily = (final_consumption * usage_hours) / 1000
        monthly = daily * days
        cost = monthly * 0.18  # Prix moyen du kWh en €

        st.markdown("---")
        st.subheader("Résultats de simulation")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Consommation quotidienne", f"{daily:.2f} kWh")
        col2.metric("Consommation mensuelle", f"{monthly:.2f} kWh")
        col3.metric("Coût estimé", f"{cost:.2f} €", "au tarif moyen de 0.18€/kWh")

        # Graphique de profil d'utilisation
        chart_data = pd.DataFrame({
            'Heures': range(24),
            'Consommation': [final_consumption/1000 if h < usage_hours else 0 for h in range(24)]
        }).set_index('Heures')
        
        st.area_chart(chart_data, height=200, use_container_width=True)
    else:
        st.warning("Veuillez renseigner la consommation électrique et les heures d'utilisation")

else:
    st.info("Veuillez entrer un modèle de climatiseur pour commencer la simulation")
