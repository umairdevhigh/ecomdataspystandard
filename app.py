import streamlit as st
import requests
from bs4 import BeautifulSoup
import csv
import re
import random
import time
from urllib.parse import urljoin
import json
import pandas as pd
from io import StringIO

# ---------- ROTATING USER-AGENTS ----------
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/126.0'
]

# ---------- REWRITER ENGINE (Copyright Bypass) ----------
class SmartRewriter:
    def __init__(self):
        self.synonyms = {
            'great': 'exceptional', 'good': 'superior', 'best': 'top-tier',
            'durable': 'long-lasting', 'strong': 'robust', 'quality': 'premium',
            'design': 'aesthetic', 'feature': 'attribute', 'product': 'item',
            'amazing': 'remarkable', 'perfect': 'ideal', 'easy': 'effortless',
            'simple': 'straightforward', 'modern': 'contemporary', 'classic': 'timeless',
            'leather': 'premium hide', 'jacket': 'outerwear', 'biker': 'motorcycle'
        }
        self.intros = [
            "Discover the unrivaled ", "Experience next-level ",
            "Upgrade your lifestyle with ", "Engineered for excellence, ",
            "Presenting the premium "
        ]

    def rewrite(self, text):
        if not text or len(text) < 5:
            return text
        sentences = re.split(r'(?<=[.!?]) +', text)
        if len(sentences) > 2:
            random.shuffle(sentences)
        new_sentences = []
        for sent in sentences:
            words = sent.split()
            new_words = []
            for word in words:
                lower_word = word.lower().strip('.,!?')
                if lower_word in self.synonyms:
                    replacement = self.synonyms[lower_word]
                    if word[0].isupper():
                        replacement = replacement.capitalize()
                    if word.endswith('.'):
                        replacement += '.'
                    new_words.append(replacement)
                else:
                    new_words.append(word)
            new_sentences.append(' '.join(new_words))
        rewritten = '. '.join(new_sentences)
        if len(rewritten) > 20:
            intro = random.choice(self.intros)
            rewritten = intro + rewritten[0].lower() + rewritten[1:]
        return rewritten.strip()

# ---------- SAFE EXTRACTORS ----------
def safe_get_offer_price(offers):
    if isinstance(offers, dict):
        return offers.get('price', '')
    elif isinstance(offers, list) and len(offers) > 0:
        first = offers[0]
        if isinstance(first, dict):
            return first.get('price', '')
    return ''

def safe_get_sku(sku_data):
    if isinstance(sku_data, str):
        return sku_data
    elif isinstance(sku_data, list) and len(sku_data) > 0:
        return str(sku_data[0])
    return ''

def format_category(breadcrumb_soup, default="Imported Products"):
    if not breadcrumb_soup:
        return default
    links = breadcrumb_soup.find_all('a')
    if len(links) > 1:
        # Last link se category lo, ya full path banao
        categories = [link.get_text(strip=True) for link in links[1:]]  # Skip Home
        if categories:
            return ' > '.join(categories)
    return default

# ---------- SCRAPER (RETURN SIMPLE LEATHER STORE FORMAT) ----------
def scrape_product(url, session):
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    
    for attempt in range(2):
        try:
            resp = session.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            break
        except:
            if attempt == 0:
                time.sleep(5)
            else:
                return None, f"Fetch failed"

    soup = BeautifulSoup(resp.text, 'lxml')
    base_url = f"{resp.url.split('/')[0]}//{resp.url.split('/')[2]}"
    product_data = {}
    
    # Parse JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            data_type = data.get('@type')
            is_product = False
            if isinstance(data_type, str) and data_type == 'Product':
                is_product = True
            elif isinstance(data_type, list) and 'Product' in data_type:
                is_product = True
            if is_product:
                product_data = data
                break
        except:
            pass

    # ---------- TITLE ----------
    title = product_data.get('name') or (soup.find('h1').get_text(strip=True) if soup.find('h1') else None)
    if not title:
        og_title = soup.find('meta', property='og:title')
        title = og_title.get('content') if og_title else url.split('/')[-1].replace('-', ' ')

    # ---------- DESCRIPTION (For rewriting) ----------
    desc = product_data.get('description') or ''
    if not desc:
        desc_meta = soup.find('meta', attrs={'name': 'description'})
        desc = desc_meta.get('content') if desc_meta else ''
    if not desc or len(desc) < 20:
        og_desc = soup.find('meta', property='og:description')
        desc = og_desc.get('content') if og_desc else title

    # ---------- PRICE ----------
    price = safe_get_offer_price(product_data.get('offers'))
    if not price:
        price_span = soup.find('span', {'class': re.compile(r'price|amount|sale-price')})
        if price_span:
            match = re.search(r'[\d,]+\.?\d*', price_span.get_text())
            price = match.group() if match else '0'
        else:
            price = '0'

    # ---------- SKU & REGENERATE ----------
    sku_raw = safe_get_sku(product_data.get('sku'))
    if not sku_raw:
        sku_span = soup.find('span', {'class': re.compile(r'sku|id|model')})
        sku_raw = sku_span.get_text(strip=True) if sku_span else f"OLD-{random.randint(1000,9999)}"
    
    rand_suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=4))
    new_parent_sku = f"CUSTOM-{rand_suffix}-{sku_raw}"

    # ---------- IMAGES ----------
    images = []
    if product_data.get('image'):
        if isinstance(product_data['image'], list):
            images.extend(product_data['image'])
        else:
            images.append(product_data['image'])
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        images.append(og_img.get('content'))
    for img in soup.find_all('img'):
        src = img.get('data-src') or img.get('src')
        if src and not src.endswith('.svg') and 'logo' not in src.lower():
            full_url = urljoin(base_url, src)
            if full_url not in images:
                images.append(full_url)
    images = [im for im in images if im.startswith('http')][:10]
    images_str = ', '.join(images)

    # ---------- CATEGORY (Proper > format) ----------
    bread = soup.find('ul', {'class': re.compile(r'breadcrumb|breadcrumbs')})
    category_str = format_category(bread, "Imported Products")
    if not category_str or category_str == "Imported Products":
        # Try to get from JSON-LD
        cat_from_ld = product_data.get('category', '')
        if cat_from_ld:
            category_str = cat_from_ld

    # ---------- REWRITE ----------
    rewriter = SmartRewriter()
    new_title = rewriter.rewrite(title)
    # We don't need description in this simple format, but keeping for potential use.
    # The sample format doesn't have a description column, so we skip it.

    # ---------- CHECK VARIABLE PRODUCT (Multiple offers) ----------
    offers = product_data.get('offers')
    variations_data = []
    if isinstance(offers, list) and len(offers) > 1:
        for offer in offers:
            if isinstance(offer, dict):
                var_sku = offer.get('sku', f'VAR-{len(variations_data)+1}')
                var_price = offer.get('price', price)
                var_attrs = {}
                # Try to find attributes like size, color, material
                if 'size' in offer:
                    var_attrs['Size'] = offer['size']
                if 'color' in offer:
                    var_attrs['Color'] = offer['color']
                # If no explicit attr, put a generic one
                if not var_attrs:
                    var_attrs['Option'] = f'Variant {len(variations_data)+1}'
                variations_data.append({
                    'sku': var_sku,
                    'price': var_price,
                    'attrs': var_attrs,
                    'image': offer.get('image', '')
                })

    # ---------- BUILD PARENT ROW (Type = variable or simple) ----------
    if variations_data:
        product_type = 'variable'
        parent_price = ''  # Variable product mein Regular price empty rakho
    else:
        product_type = 'simple'
        parent_price = price

    # --- Attribute collection for Parent ---
    attr_names = set()
    attr_values_map = {}
    if variations_data:
        for var in variations_data:
            for key, val in var['attrs'].items():
                attr_names.add(key)
                if key not in attr_values_map:
                    attr_values_map[key] = set()
                attr_values_map[key].add(val)
    
    # Convert sets to sorted list for consistent output
    attr_names = sorted(list(attr_names))
    
    # Prepare attribute columns (Max 2 as per sample, but we'll support up to 3 if needed)
    attr_cols = {'Attribute 1 name': '', 'Attribute 1 value(s)': '', 
                 'Attribute 2 name': '', 'Attribute 2 value(s)': ''}
    
    if attr_names:
        for i, name in enumerate(attr_names[:2]):  # Only top 2 attributes (sample has 2)
            vals = sorted(list(attr_values_map[name]))
            attr_cols[f'Attribute {i+1} name'] = name
            attr_cols[f'Attribute {i+1} value(s)'] = ' | '.join(vals)  # Pipe separated as per sample

    parent_row = {
        'Type': product_type,
        'SKU': new_parent_sku,
        'Name': new_title,
        'Published': 1,
        'Regular price': parent_price,
        'Categories': category_str,
        'Images': images_str,
        'Attribute 1 name': attr_cols['Attribute 1 name'],
        'Attribute 1 value(s)': attr_cols['Attribute 1 value(s)'],
        'Attribute 2 name': attr_cols['Attribute 2 name'],
        'Attribute 2 value(s)': attr_cols['Attribute 2 value(s)'],
        'Parent': '',  # Parent ka Parent empty
        'Stock': 10 if product_type == 'simple' else ''  # Variable mein stock empty
    }

    results = [parent_row]

    # ---------- BUILD VARIATIONS (Child rows) ----------
    if variations_data:
        for var in variations_data:
            # Build variation SKU: parent_sku + suffix
            var_sku = f"{new_parent_sku}-{var.get('sku', random.randint(100,999))}"
            var_price = var.get('price', price)
            var_img = var.get('image', '')
            
            # Prepare variation attribute values (single, not pipe-separated)
            var_attrs = var['attrs']
            attr1_val = ''
            attr2_val = ''
            attr1_name = ''
            attr2_name = ''
            
            # Get attribute names from parent (or direct)
            all_attr_names = list(var_attrs.keys())
            if all_attr_names:
                attr1_name = all_attr_names[0]
                attr1_val = var_attrs[attr1_name]
            if len(all_attr_names) > 1:
                attr2_name = all_attr_names[1]
                attr2_val = var_attrs[attr2_name]

            variation_row = {
                'Type': 'variation',
                'SKU': var_sku,
                'Name': f"{new_title} - {attr1_val} {attr2_val}".strip() if (attr1_val or attr2_val) else f"{new_title} - Var",
                'Published': 1,
                'Regular price': var_price,
                'Categories': category_str,
                'Images': var_img if var_img else images_str,
                'Attribute 1 name': attr1_name,
                'Attribute 1 value(s)': attr1_val,
                'Attribute 2 name': attr2_name,
                'Attribute 2 value(s)': attr2_val,
                'Parent': new_parent_sku,  # CRUCIAL: SKU-based linking
                'Stock': 10
            }
            results.append(variation_row)
    
    return results, None

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Leather Store CSV Generator", page_icon="🧥")
st.title("🧥 WooCommerce CSV Generator (Leather Store Format)")
st.markdown("**Exact 13-Column Format | Auto Variable Products | Rewrite + SKU Change**")

with st.expander("📌 Format Details", expanded=True):
    st.write("""
    - **Columns:** Type, SKU, Name, Published, Regular price, Categories, Images, Attribute 1 name, Attribute 1 value(s), Attribute 2 name, Attribute 2 value(s), Parent, Stock.
    - **Parent Linking:** Variations ke `Parent` column mein **Parent ki SKU** daali jayegi (jaise sample mein hai).
    - **Attributes:** Parent par `S | M | L` (pipe separated), Variations par specific value (e.g., `S`).
    - **Anti-Block:** 4-6 sec delay, rotating user-agents, auto-retry.
    - **SKU Change:** Har product ka SKU `CUSTOM-XXXX-OLD_SKU` format mein change ho jayega (duplicate/copyright se bachne ke liye).
    """)

urls_input = st.text_area("🔗 Paste Product URLs (20-30 recommended per batch):", height=150, 
                          placeholder="https://www.thejacketmaker.com/products/ionic-black-leather-jacket, https://example.com/product2")

# Exact columns matching the sample
EXACT_COLUMNS = [
    'Type', 'SKU', 'Name', 'Published', 'Regular price', 'Categories', 'Images',
    'Attribute 1 name', 'Attribute 1 value(s)', 'Attribute 2 name', 'Attribute 2 value(s)',
    'Parent', 'Stock'
]

if st.button("🚀 Generate Leather Store CSV", type="primary"):
    if not urls_input.strip():
        st.error("❌ Kuch URLs toh daalo!")
    else:
        urls = [u.strip() for u in re.split(r'[,\s]+', urls_input) if u.strip().startswith('http')]
        if not urls:
            st.error("❌ Valid URL nahi mili.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            all_rows = []
            failed_urls = []
            
            session = requests.Session()
            
            for idx, url in enumerate(urls):
                status_text.text(f"⏳ Processing {idx+1}/{len(urls)} (Slow mode ON)...")
                results, error = scrape_product(url, session)
                if results:
                    all_rows.extend(results)
                else:
                    failed_urls.append(url)
                
                progress_bar.progress((idx + 1) / len(urls))
                # CRUCIAL: 4-6 second delay
                time.sleep(random.uniform(4.0, 6.5))
            
            progress_bar.progress(1.0)
            status_text.text("✅ Complete!")
            
            if all_rows:
                df = pd.DataFrame(all_rows, columns=EXACT_COLUMNS)
                for col in EXACT_COLUMNS:
                    if col not in df.columns:
                        df[col] = ''
                df = df[EXACT_COLUMNS]
                
                csv_buffer = StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_data = csv_buffer.getvalue()
                
                st.success(f"🎯 {len(all_rows)} rows generated! {len(failed_urls)} failed.")
                if failed_urls:
                    st.warning(f"⚠️ {len(failed_urls)} URLs failed. Inhe alag se daal kar try karo (temporary block).")
                
                st.subheader("📊 Preview (First 5 rows)")
                st.dataframe(df.head(5))
                
                st.download_button(
                    label="⬇️ Download Leather Store CSV",
                    data=csv_data,
                    file_name=f"leather_store_import_{int(time.time())}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.error("❌ Koi product scrape nahi ho saka. Network/site block check karo.")

st.caption("🧥 Cunning Leather Store Mode: SKU linking | Pipe-separated attributes | Rewritten titles")
