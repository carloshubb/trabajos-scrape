import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re
import csv
import time
from urllib.parse import urljoin

BASE_URL = "https://trabajosdiarios.co.cr"

# List of all locations to scrape
LOCATIONS = [
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-san-jose",
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-alajuela",
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-cartago",
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-guanacaste",
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-heredia",
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-limon",
    "https://trabajosdiarios.co.cr/ofertas-trabajo/en-puntarenas"
]

def extract_experience(soup, job_data):
    """Extract job experience text when it's in the next <dd> tag."""
    exp_label = soup.find('span', string=re.compile(r'Experiencia requerida', re.IGNORECASE))

    if not exp_label:
        job_data['_job_experience'] = None
        return

    dt_tag = exp_label.find_parent('dt')
    if not dt_tag:
        job_data['_job_experience'] = None
        return

    dd_tag = dt_tag.find_next_sibling('dd')
    if not dd_tag:
        job_data['_job_experience'] = None
        return

    exp_text = dd_tag.get_text(strip=True)
    job_data['_job_experience'] = exp_text if exp_text else None

    print("Extracted experience:", job_data['_job_experience'])

def scrape_job_detail(url):
    """Scrape individual job listing details"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        job_data = {
            '_job_title': None,
            '_job_description': None,
            '_job_category': None,
            '_job_type': None,
            '_job_location': None,
            '_job_address': None,
            '_job_salary': None,
            '_job_salary_type': None,
            '_job_max_salary': None,
            '_job_experience': None,
            '_job_qualification': None,
            '_job_career_level': None,
            '_job_expiry_date': None,
            '_job_application_deadline_date': None,
            '_job_apply_type': None,
            '_job_apply_url': None,
            '_job_apply_email': None,
            '_job_featured': False,
            '_job_filled': False,
            '_job_urgent': False,
            '_job_featured_image': None,
            '_job_video_url': None,
            '_job_tag': 'Costa Rica',
            '_job_photos': [],
            '_job_gender': None,
            '_job_map_location': None
        }

        # --- Extract JSON-LD structured data ---
        for json_ld_script in soup.find_all('script', type='application/ld+json'):
            try:
                json_string = json_ld_script.string
                if not json_string:
                    continue
                json_string = re.sub(r'\s+', ' ', json_string.strip())
                json_ld_data = json.loads(json_string)
                if isinstance(json_ld_data, dict) and json_ld_data.get('@type') == 'JobPosting':
                    item = json_ld_data
                elif isinstance(json_ld_data, dict) and '@graph' in json_ld_data:
                    for item in json_ld_data['@graph']:
                        if item.get('@type') == 'JobPosting':
                            break
                    else:
                        continue
                else:
                    continue

                job_data['_job_title'] = item.get('title', '').strip()
                description = item.get('description', '')
                if description:
                    description = description.replace('. ', '.\r\n')
                    job_data['_job_description'] = description.strip()

                job_data['_job_expiry_date'] = item.get('validThrough')
                job_data['_job_application_deadline_date'] = item.get('validThrough')

                employment_type = item.get('employmentType', '')
                job_data['_job_type'] = {
                    'FULL_TIME': 'Tiempo Completo',
                    'PART_TIME': 'Tiempo parcial',
                    'TEMPORARY': 'Temporario',
                    'CONTRACT': 'Contrato'
                }.get(employment_type, employment_type)

                edu_req = item.get('educationRequirements', {})
                if isinstance(edu_req, dict):
                    job_data['_job_qualification'] = edu_req.get('credentialCategory', '').strip()

                job_location = item.get('jobLocation', {})
                if isinstance(job_location, dict):
                    address_data = job_location.get('address', {})
                    if isinstance(address_data, dict):
                        locality = address_data.get('addressLocality', '').strip()
                        region = address_data.get('addressRegion', '').strip()
                        if locality:
                            job_data['_job_location'] = locality
                            job_data['_job_address'] = locality
                            job_data['_job_map_location'] = locality
                        elif region:
                            job_data['_job_location'] = region
                            job_data['_job_address'] = region
                            job_data['_job_map_location'] = region

                salary_data = item.get('baseSalary', {})
                if isinstance(salary_data, dict):
                    value_data = salary_data.get('value', {})
                    if isinstance(value_data, dict):
                        salary_value = value_data.get('value')
                        if isinstance(salary_value, (int, float, str)):
                            job_data['_job_salary'] = str(salary_value).strip()

                        unit_text = value_data.get('unitText', '')
                        job_data['_job_salary_type'] = {
                            'MONTH': 'mensual',
                            'YEAR': 'anual',
                            'HOUR': 'hora'
                        }.get(unit_text, '')

            except Exception:
                continue

        # --- Fallback title ---
        if not job_data['_job_title']:
            title_elem = soup.find('h1')
            if title_elem:
                job_data['_job_title'] = title_elem.get_text(strip=True)

        # --- Featured / filled / urgent badges detection ---
        premium_badge = soup.find('span', class_=re.compile('premium', re.IGNORECASE)) \
                        or soup.find(string=re.compile('Premium', re.IGNORECASE))
        if premium_badge:
            job_data['_job_featured'] = True

        if soup.find(string=re.compile(r'\b(llenad[oa]|filled)\b', re.IGNORECASE)):
            job_data['_job_filled'] = True
        if soup.find(string=re.compile(r'\b(urgente|urgent)\b', re.IGNORECASE)):
            job_data['_job_urgent'] = True

        # --- Extract visible description ---
        if not job_data['_job_description']:
            content_candidates = []

            for selector in [
                'div.job-description', 'div.job-details', 'div.description', 'div.oferta-descripcion',
                '#job-description', '.descripcion', '.job-content'
            ]:
                el = soup.select_one(selector)
                if el:
                    content_candidates.append(el)

            detail_section = soup.find(['h2', 'h3'], string=re.compile(r'Job details|Detalle del empleo|Descripción|Descripción del puesto', re.IGNORECASE))
            if detail_section:
                current = detail_section.find_next_sibling()
                collected = []
                while current and current.name not in ['h1', 'h2', 'h3']:
                    collected.append(current)
                    current = current.find_next_sibling()
                if collected:
                    wrapper = BeautifulSoup("<div></div>", "html.parser").div
                    for node in collected:
                        wrapper.append(node)
                    content_candidates.append(wrapper)

            if not content_candidates:
                paragraphs = soup.find_all('p')
                if paragraphs:
                    wrapper = BeautifulSoup("<div></div>", "html.parser").div
                    for p in paragraphs:
                        wrapper.append(p)
                    content_candidates.append(wrapper)

            best_text = None
            best_len = 0
            for cand in content_candidates:
                text = cand.get_text(separator="\n", strip=True)
                if text and len(text) > best_len:
                    best_len = len(text)
                    best_text = text

            if best_text:
                best_text = best_text.replace('\r\n', '\n').replace('\r', '\n')
                job_data['_job_description'] = best_text

        # --- Extract experience ---
        extract_experience(soup, job_data)

        # --- Category extraction ---
        categories = []

        for sel in ['nav.breadcrumb a', 'ul.breadcrumb a', 'ol.breadcrumb a', '.breadcrumb a']:
            for a in soup.select(sel):
                txt = a.get_text(strip=True)
                if txt:
                    categories.append(txt)

        meta_kw = soup.find('meta', attrs={'name': re.compile(r'keywords', re.IGNORECASE)})
        if meta_kw and meta_kw.get('content'):
            for kw in re.split(r'[,\|;]', meta_kw['content']):
                k = kw.strip()
                if k:
                    categories.append(k)

        for sel in ['a[rel="tag"]', 'a.tag', 'a.category', '.tags a', '.categories a', 'a[href*="/categoria/"]', 'a[href*="/categoria-"]']:
            for a in soup.select(sel):
                txt = a.get_text(strip=True)
                if txt:
                    categories.append(txt)

        seen_cats = []
        for c in categories:
            cleaned = re.sub(r'\s+', ' ', c).strip()
            if cleaned and cleaned.lower() not in (s.lower() for s in seen_cats):
                seen_cats.append(cleaned)

        if seen_cats:
            job_data['_job_category'] = ','.join(seen_cats)

        # --- Featured image ---
        img_elem = soup.find('img', src=re.compile(r'\.(jpg|png|jpeg|webp)', re.IGNORECASE))
        if img_elem and img_elem.get('src'):
            src = img_elem['src']
            if src.startswith('http'):
                job_data['_job_featured_image'] = src
            elif src.startswith('//'):
                job_data['_job_featured_image'] = 'https:' + src
            elif src.startswith('/'):
                job_data['_job_featured_image'] = BASE_URL + src

        # --- Apply info ---
        job_data['_job_apply_type'] = 'external'
        job_data['_job_apply_url'] = url
        job_data['_job_max_salary'] = job_data['_job_salary']

        return job_data

    except Exception as e:
        print(f"  Error scraping job detail: {str(e)}")
        return None


def scrape_job_listings(list_url, max_pages=5, max_jobs=None):
    """Scrape multiple job listings from listing page"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/91.0.4472.124 Safari/537.36'
    }

    all_jobs, seen = [], set()
    page = 1

    while page <= max_pages:
        try:
            url = f"{list_url}{'&' if '?' in list_url else '?'}page={page}" if page > 1 else list_url
            print(f"\nScraping page {page}: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            job_links = []
            for link in soup.find_all('a', href=re.compile(r'/trabajo/\d+/')):
                job_url = urljoin(BASE_URL, link['href'])
                if job_url not in job_links:
                    job_links.append(job_url)

            job_containers = soup.find_all(['article', 'div'], class_=re.compile(r'job|oferta|trabajo', re.IGNORECASE))
            for container in job_containers:
                link = container.find('a', href=re.compile(r'/trabajo/'))
                if link:
                    job_url = urljoin(BASE_URL, link['href'])
                    if job_url not in job_links:
                        job_links.append(job_url)

            if not job_links:
                print(f"  No job links found on page {page}")
                break

            print(f"  Found {len(job_links)} jobs")
            for job_url in job_links:
                if max_jobs and len(all_jobs) >= max_jobs:
                    print(f"\n✓ Reached maximum of {max_jobs} jobs")
                    return all_jobs

                if job_url in seen:
                    continue
                seen.add(job_url)

                print(f"  [{len(all_jobs) + 1}] Scraping: {job_url}")
                job_data = scrape_job_detail(job_url)
                if job_data:
                    all_jobs.append(job_data)
                    title = job_data.get('_job_title', 'Unknown')
                    print(f"      ✓ {title}")
                time.sleep(1)

            next_button = soup.find('a', string=re.compile(r'Siguiente|Next', re.IGNORECASE)) \
                          or soup.select_one('li.next a, a[rel="next"]')
            if not next_button:
                print("\n✓ No more pages found")
                break

            page += 1
            time.sleep(2)

        except Exception as e:
            print(f"Error scraping listing page: {str(e)}")
            break

    return all_jobs


def save_jobs_to_csv(jobs, filename='trabajos_diarios_jobs.csv'):
    """Save all jobs to CSV"""
    if not jobs:
        print("No jobs to save")
        return

    fieldnames = [
        '_job_title', '_job_description', '_job_category', '_job_type', '_job_location',
        '_job_address', '_job_salary', '_job_salary_type', '_job_max_salary',
        '_job_experience', '_job_qualification', '_job_career_level',
        '_job_expiry_date', '_job_application_deadline_date',
        '_job_apply_type', '_job_apply_url', '_job_apply_email',
        '_job_featured', '_job_filled', '_job_urgent', '_job_featured_image', '_job_video_url',
        '_job_tag', '_job_photos', '_job_gender', '_job_map_location'
    ]

    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore', quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        for job in jobs:
            csv_data = {}
            for key in fieldnames:
                value = job.get(key)
                if isinstance(value, list):
                    csv_data[key] = ','.join(str(v) for v in value) if value else ''
                elif isinstance(value, bool):
                    csv_data[key] = 1 if value else 0
                elif value is None:
                    csv_data[key] = ''
                else:
                    if key == '_job_description' and isinstance(value, str):
                        csv_data[key] = value.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')
                    else:
                        csv_data[key] = value
            writer.writerow(csv_data)

    print(f"✓ {len(jobs)} jobs saved to {filename}")


def save_jobs_to_json(jobs, filename='trabajos_diarios_jobs.json'):
    """Save all jobs to JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
    print(f"✓ {len(jobs)} jobs saved to {filename}")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    max_pages_per_location = 3
    max_jobs_per_location = None  # Set to a number to limit jobs per location

    print("=" * 70)
    print("TRABAJOS DIARIOS - MULTI-LOCATION JOB SCRAPER")
    print("=" * 70)
    print(f"Locations to scrape: {len(LOCATIONS)}")
    print(f"Max Pages per location: {max_pages_per_location}")
    print(f"Max Jobs per location: {max_jobs_per_location if max_jobs_per_location else 'All'}")
    print("=" * 70)

    all_jobs = []
    
    for i, location_url in enumerate(LOCATIONS, 1):
        location_name = location_url.split('/')[-1].replace('en-', '').title()
        print(f"\n{'='*70}")
        print(f"LOCATION {i}/{len(LOCATIONS)}: {location_name}")
        print(f"{'='*70}")
        
        jobs = scrape_job_listings(location_url, max_pages=max_pages_per_location, max_jobs=max_jobs_per_location)
        all_jobs.extend(jobs)
        
        print(f"\n✓ Collected {len(jobs)} jobs from {location_name}")
        print(f"Total jobs so far: {len(all_jobs)}")
        
        # Wait between locations to be polite
        if i < len(LOCATIONS):
            print("\nWaiting 5 seconds before next location...")
            time.sleep(5)

    if all_jobs:
        print("\n" + "=" * 70)
        print(f"SCRAPING COMPLETE - {len(all_jobs)} total jobs collected")
        print("=" * 70)
        save_jobs_to_csv(all_jobs)
        save_jobs_to_json(all_jobs)
        print("\n✓ All done!")
    else:
        print("\n✗ No jobs were scraped")