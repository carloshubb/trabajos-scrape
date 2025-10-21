import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re
import csv
import time
from urllib.parse import urljoin

def scrape_job_detail(url):
    """
    Scrape individual job listing details
    Returns a dictionary with all the required fields
    """
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Initialize data dictionary with _job_ prefix
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
            '_job_tag': [],
            '_job_photos': [],
            '_job_gender': None,
            '_job_map_location': None
        }
        
        # Extract JSON-LD structured data
        json_ld_script = soup.find('script', type='application/ld+json')
        if json_ld_script:
            try:
                json_string = json_ld_script.string
                if json_string:
                    json_string = json_string.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                    json_string = re.sub(r'\s+', ' ', json_string)
                    
                json_ld_data = json.loads(json_string)
                
                if '@graph' in json_ld_data:
                    for item in json_ld_data['@graph']:
                        if item.get('@type') == 'JobPosting':
                            job_data['_job_title'] = item.get('title', '').strip()
                            
                            # Preserve EXACT line breaks in description - keep ALL original formatting
                            description = item.get('description', '')
                            if description:
                                # Keep original newlines exactly as they are
                                # Only normalize carriage returns to standard newlines
                                description = description.replace('\r\n', '\n').replace('\r', '\n')
                                # Strip only leading/trailing whitespace, NOT internal newlines
                                lines = description.split('\n')
                                # Strip each line but keep the newlines between them
                                cleaned_lines = [line.strip() for line in lines]
                                job_data['_job_description'] = '\n'.join(cleaned_lines)
                            
                            job_data['_job_expiry_date'] = item.get('validThrough')
                            job_data['_job_application_deadline_date'] = item.get('validThrough')
                            
                            employment_type = item.get('employmentType', '')
                            if employment_type == 'FULL_TIME':
                                job_data['_job_type'] = 'Full Time'
                            elif employment_type == 'PART_TIME':
                                job_data['_job_type'] = 'Part Time'
                            elif employment_type == 'TEMPORARY':
                                job_data['_job_type'] = 'Temporary'
                            elif employment_type == 'CONTRACT':
                                job_data['_job_type'] = 'Contract'
                            else:
                                job_data['_job_type'] = employment_type
                            
                            edu_req = item.get('educationRequirements', {})
                            if isinstance(edu_req, dict):
                                job_data['_job_qualification'] = edu_req.get('credentialCategory', '').strip()
                            
                            # Extract experience requirements
                            exp_req = item.get('experienceRequirements', {})
                            if isinstance(exp_req, dict):
                                exp_value = exp_req.get('monthsOfExperience')
                                if exp_value:
                                    years = int(exp_value) / 12
                                    if years >= 1:
                                        job_data['_job_experience'] = f"{int(years)} year{'s' if years != 1 else ''}"
                                    else:
                                        job_data['_job_experience'] = f"{exp_value} months"
                            
                            # Extract job category
                            occ_category = item.get('occupationalCategory', '')
                            if occ_category:
                                job_data['_job_category'] = occ_category.strip()
                            
                            # Alternative category from industry
                            if not job_data['_job_category']:
                                industry = item.get('industry', '')
                                if industry:
                                    job_data['_job_category'] = industry.strip()
                            
                            job_location = item.get('jobLocation', {})
                            if isinstance(job_location, dict):
                                address_data = job_location.get('address', {})
                                if isinstance(address_data, dict):
                                    locality = address_data.get('addressLocality', '').strip()
                                    region = address_data.get('addressRegion', '').strip()
                                    
                                    # Extract only the locality (first part before comma)
                                    if locality:
                                        job_data['_job_location'] = locality
                                        job_data['_job_address'] = locality
                                    elif region:
                                        job_data['_job_location'] = region
                                        job_data['_job_address'] = region
                            
                            salary_data = item.get('baseSalary', {})
                            if isinstance(salary_data, dict):
                                value_data = salary_data.get('value', {})
                                if isinstance(value_data, dict):
                                    salary_value = value_data.get('value')
                                    job_data['_job_salary'] = salary_value
                                    job_data['_job_max_salary'] = salary_value  # Same as salary
                                    unit_text = value_data.get('unitText', '')
                                    if unit_text == 'MONTH':
                                        job_data['_job_salary_type'] = 'Monthly'
                                    elif unit_text == 'YEAR':
                                        job_data['_job_salary_type'] = 'Yearly'
                                    elif unit_text == 'HOUR':
                                        job_data['_job_salary_type'] = 'Hourly'
            
            except json.JSONDecodeError as e:
                print(f"  Warning: Error parsing JSON-LD: {e}")
        
        # Extract title from HTML if not found
        if not job_data['_job_title']:
            title_elem = soup.find('h1')
            if title_elem:
                job_data['_job_title'] = title_elem.get_text(strip=True)
        
        # Check for Premium badge
        premium_badge = soup.find('span', class_=re.compile('premium', re.IGNORECASE)) or soup.find(string=re.compile('Premium', re.IGNORECASE))
        if premium_badge:
            job_data['_job_featured'] = True
        
        # Extract description from visible content with preserved line breaks
        if not job_data['_job_description']:
            desc_parts = []
            
            # Find the "Detalle del empleo" section
            details_section = soup.find(['h2', 'h3', 'div'], string=re.compile(r'Detalle del empleo', re.IGNORECASE))
            
            if details_section:
                # Find the parent container
                container = details_section.find_parent()
                if container:
                    # Look for all text after the heading, line by line
                    # Find all text nodes that are direct content
                    for elem in container.find_all(['p', 'div', 'span'], recursive=True):
                        text = elem.get_text('\n', strip=True)  # Use \n as separator
                        if (text and 
                            len(text) > 3 and 
                            'schema.org' not in text and 
                            '@type' not in text and
                            'Detalle del empleo' not in text and
                            'Publicado' not in text):
                            # Split by newlines to get individual lines
                            lines = text.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and len(line) > 3:
                                    desc_parts.append(line)
            
            # Alternative method: look for the description in a specific div/section
            if not desc_parts:
                # Try to find paragraphs or list items with job details
                job_detail_keywords = ['educación', 'experiencia', 'gestión', 'coordinación', 
                                      'mantenimiento', 'limpieza', 'responsabilidad']
                
                for p in soup.find_all(['p', 'li', 'div']):
                    text = p.get_text(strip=True)
                    if (len(text) > 15 and 
                        len(text) < 500 and  # Not too long (avoid entire blocks)
                        'schema.org' not in text and 
                        '@type' not in text and
                        any(keyword in text.lower() for keyword in job_detail_keywords)):
                        desc_parts.append(text)
            
            if desc_parts:
                # Remove duplicates while preserving order
                seen = set()
                unique_parts = []
                for part in desc_parts:
                    if part not in seen and len(part) > 3:
                        seen.add(part)
                        unique_parts.append(part)
                
                # Join with newline to preserve line breaks
                job_data['_job_description'] = '\n'.join(unique_parts[:25])
        
        # Extract location from HTML if not found
        if not job_data['_job_location']:
            location_elem = soup.find(string=re.compile(r'Ubicación:', re.IGNORECASE))
            if location_elem:
                parent = location_elem.find_parent()
                if parent:
                    full_text = parent.get_text(strip=True)
                    location_text = full_text.replace('Ubicación:', '').strip()
                    # Extract only the first part before comma
                    if ',' in location_text:
                        job_data['_job_location'] = location_text.split(',')[0].strip()
                    else:
                        job_data['_job_location'] = location_text
                    job_data['_job_address'] = job_data['_job_location']
        
        # Extract experience
        if not job_data['_job_experience']:
            exp_elem = soup.find(string=re.compile(r'Experiencia requerida:', re.IGNORECASE))
            if exp_elem:
                exp_parent = exp_elem.find_parent()
                if exp_parent:
                    exp_text = exp_parent.get_text(strip=True)
                    exp_text_clean = re.sub(r'Experiencia requerida:\s*', '', exp_text, flags=re.IGNORECASE)
                    if exp_text_clean and len(exp_text_clean) < 50:
                        job_data['_job_experience'] = exp_text_clean
        
        # Extract category from breadcrumb or page content
        if not job_data['_job_category']:
            # Try to find category from breadcrumbs
            breadcrumb = soup.find('ol', class_=re.compile('breadcrumb', re.IGNORECASE))
            if breadcrumb:
                breadcrumb_items = breadcrumb.find_all('li')
                if len(breadcrumb_items) > 2:
                    # Usually the category is in the breadcrumb
                    category_text = breadcrumb_items[-2].get_text(strip=True)
                    if category_text and category_text not in ['Home', 'Búsqueda', 'Search']:
                        job_data['_job_category'] = category_text
            
            # Alternative: extract from title keywords
            if not job_data['_job_category'] and job_data['_job_title']:
                title_lower = job_data['_job_title'].lower()
                if any(word in title_lower for word in ['limpieza', 'cleaning', 'mantenimiento']):
                    job_data['_job_category'] = 'Cleaning & Maintenance'
                elif any(word in title_lower for word in ['coordinador', 'coordinator', 'gerente', 'manager']):
                    job_data['_job_category'] = 'Management'
                elif any(word in title_lower for word in ['vendedor', 'ventas', 'sales']):
                    job_data['_job_category'] = 'Sales'
                elif any(word in title_lower for word in ['contador', 'contabilidad', 'accounting']):
                    job_data['_job_category'] = 'Accounting & Finance'
        
        # Extract qualification
        if not job_data['_job_qualification']:
            qual_elem = soup.find(string=re.compile(r'Educación requerida:', re.IGNORECASE))
            if qual_elem:
                qual_parent = qual_elem.find_parent()
                if qual_parent:
                    qual_text = qual_parent.get_text(strip=True)
                    qual_text_clean = re.sub(r'Educación requerida:\s*', '', qual_text, flags=re.IGNORECASE)
                    if qual_text_clean and len(qual_text_clean) < 50:
                        job_data['_job_qualification'] = qual_text_clean
        
        # Extract contract type
        if not job_data['_job_type']:
            type_elem = soup.find(string=re.compile(r'Tipo de Contrato:|Tiempo Completo|Tiempo Parcial', re.IGNORECASE))
            if type_elem:
                type_parent = type_elem.find_parent()
                if type_parent:
                    type_text = type_parent.get_text(strip=True)
                    if 'Tiempo Completo' in type_text or 'Full Time' in type_text:
                        job_data['_job_type'] = 'Full Time'
                    elif 'Tiempo Parcial' in type_text or 'Part Time' in type_text:
                        job_data['_job_type'] = 'Part Time'
                    elif 'Temporal' in type_text:
                        job_data['_job_type'] = 'Temporary'
                    elif 'Por Contrato' in type_text:
                        job_data['_job_type'] = 'Contract'
        
        # Extract featured image
        img_elem = soup.find('img', src=re.compile(r'\.(jpg|png|jpeg|webp)', re.IGNORECASE))
        if img_elem and img_elem.get('src'):
            src = img_elem['src']
            if src.startswith('http'):
                job_data['_job_featured_image'] = src
            elif src.startswith('//'):
                job_data['_job_featured_image'] = 'https:' + src
            elif src.startswith('/'):
                job_data['_job_featured_image'] = 'https://trabajosdiarios.co.cr' + src
        
        # Set apply info
        job_data['_job_apply_type'] = 'url'
        job_data['_job_apply_url'] = url
        
        # Set max_salary same as salary if salary exists
        if job_data['_job_salary'] and not job_data['_job_max_salary']:
            job_data['_job_max_salary'] = job_data['_job_salary']
        
        return job_data
        
    except Exception as e:
        print(f"  Error scraping job detail: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def scrape_job_listings(list_url, max_pages=5, max_jobs=None):
    """
    Scrape multiple job listings from the listing page
    """
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    all_jobs = []
    page = 1
    
    while page <= max_pages:
        try:
            # Construct URL with page number
            if page == 1:
                url = list_url
            else:
                # Handle pagination URL format
                if '?' in list_url:
                    url = f"{list_url}&page={page}"
                else:
                    url = f"{list_url}?page={page}"
            
            print(f"\nScraping page {page}: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all job links
            job_links = []
            
            # Method 1: Find links with job titles
            for link in soup.find_all('a', href=re.compile(r'/trabajo/\d+/')):
                job_url = urljoin('https://trabajosdiarios.co.cr', link['href'])
                if job_url not in job_links:
                    job_links.append(job_url)
            
            # Method 2: Find article/div containers with job postings
            job_containers = soup.find_all(['article', 'div'], class_=re.compile(r'job|oferta|trabajo', re.IGNORECASE))
            for container in job_containers:
                link = container.find('a', href=re.compile(r'/trabajo/'))
                if link:
                    job_url = urljoin('https://trabajosdiarios.co.cr', link['href'])
                    if job_url not in job_links:
                        job_links.append(job_url)
            
            if not job_links:
                print(f"  No job links found on page {page}")
                break
            
            print(f"  Found {len(job_links)} jobs on this page")
            
            # Scrape each job
            for idx, job_url in enumerate(job_links, 1):
                if max_jobs and len(all_jobs) >= max_jobs:
                    print(f"\n✓ Reached maximum of {max_jobs} jobs")
                    return all_jobs
                
                print(f"  [{len(all_jobs) + 1}] Scraping: {job_url}")
                job_data = scrape_job_detail(job_url)
                
                if job_data:
                    all_jobs.append(job_data)
                    title = job_data.get('_job_title', 'Unknown')
                    print(f"      ✓ {title}")
                
                # Be polite - add delay between requests
                time.sleep(1)
            
            # Check if there's a next page
            next_button = soup.find('a', string=re.compile(r'Siguiente|Next', re.IGNORECASE))
            if not next_button:
                print(f"\n✓ No more pages found")
                break
            
            page += 1
            time.sleep(2)  # Delay between pages
            
        except Exception as e:
            print(f"Error scraping listing page: {str(e)}")
            import traceback
            traceback.print_exc()
            break
    
    return all_jobs


def save_jobs_to_csv(jobs, filename='trabajos_diarios_jobs.csv'):
    """Save all jobs to CSV file with proper newline handling"""
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
    
    # Use lineterminator='\n' and quoting to preserve newlines in fields
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore', quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for job in jobs:
            # Only include fields that are in fieldnames
            csv_data = {}
            for key in fieldnames:
                value = job.get(key)
                if isinstance(value, list):
                    csv_data[key] = ', '.join(str(v) for v in value) if value else ''
                elif value is None:
                    csv_data[key] = ''
                else:
                    # Keep newlines as-is in the data
                    csv_data[key] = value
            writer.writerow(csv_data)
    
    print(f"✓ {len(jobs)} jobs saved to {filename}")


def save_jobs_to_json(jobs, filename='trabajos_diarios_jobs.json'):
    """Save all jobs to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
    print(f"✓ {len(jobs)} jobs saved to {filename}")


# Main execution
if __name__ == "__main__":
    # Configuration
    listing_url = "https://trabajosdiarios.co.cr/ofertas-trabajo/en-san-jose"
    max_pages_to_scrape = 3  # Adjust this number
    max_jobs_to_scrape = None  # Set to a number to limit, or None for all
    
    print("="*70)
    print("TRABAJOS DIARIOS - JOB SCRAPER")
    print("="*70)
    print(f"Target URL: {listing_url}")
    print(f"Max Pages: {max_pages_to_scrape}")
    print(f"Max Jobs: {max_jobs_to_scrape if max_jobs_to_scrape else 'All'}")
    print("="*70)
    
    # Scrape all jobs
    jobs = scrape_job_listings(listing_url, max_pages=max_pages_to_scrape, max_jobs=max_jobs_to_scrape)
    
    if jobs:
        print("\n" + "="*70)
        print(f"SCRAPING COMPLETE - {len(jobs)} jobs collected")
        print("="*70)
        
        # Display summary
        print("\nJob Summary:")
        for idx, job in enumerate(jobs, 1):
            location = job.get('_job_location', 'N/A')
            title = job.get('_job_title', 'N/A')
            print(f"  {idx}. {title} ({location})")
        
        # Save to files
        print("\nSaving data...")
        save_jobs_to_csv(jobs)
        save_jobs_to_json(jobs)
        
        print("\n✓ All done!")
    else:
        print("\n✗ No jobs were scraped")