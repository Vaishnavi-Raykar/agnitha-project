import argparse
import sys
import logging
from typing import List, Dict, Optional, Tuple
import pandas as pd
from Bio import Entrez

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Provide your email address to NCBI Entrez
Entrez.email = "vraykar232@gmail.com" # Replace with a valid email

# Keywords to identify pharmaceutical/biotech companies (expand as needed)
COMPANY_KEYWORDS = [
    "inc", "ltd", "llc", "corp", "corporation", "pharma", "pharmaceuticals",
    "biotech", "therapeutics", "diagnostics", "biosciences", "gmbh", "ag",
    "bv", "s.a.", "s.l.", "s.r.l."
]
# Domains often associated with academic institutions (expand as needed)
ACADEMIC_DOMAINS = [".edu", ".ac.", ".org"] # .org can be tricky, use with caution

def setup_arg_parser() -> argparse.ArgumentParser:
    """Sets up the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Fetch research papers from PubMed based on a query and filter by non-academic authors."
    )
    parser.add_argument(
        "query",
        type=str,
        help="Search query for PubMed (supports PubMed's full query syntax)."
    )
    parser.add_argument(
        "-f", "--file",
        type=str,
        help="Specify the filename to save the results as a CSV file. If not provided, prints to the console."
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Enable debug logging information during execution."
    )
    # Consider adding a limit for the number of results to fetch
    # parser.add_argument("-l", "--limit", type=int, default=100, help="Maximum number of papers to fetch.")
    return parser

def search_pubmed(query: str, retmax: int = 1000) -> List[str]:
    """Searches PubMed and returns a list of PubMed IDs (PMIDs)."""
    logger.info(f"Searching PubMed with query: {query}")
    try:
        handle = Entrez.esearch(db="pubmed", term=query, retmax=str(retmax))
        record = Entrez.read(handle)
        handle.close()
        pmids = record["IdList"]
        logger.info(f"Found {len(pmids)} potential papers.")
        return pmids
    except Exception as e:
        logger.error(f"Error searching PubMed: {e}")
        return []

def fetch_paper_details(pmids: List[str]) -> List[Dict]:
    """Fetches detailed information for a list of PMIDs."""
    if not pmids:
        return []
    logger.info(f"Fetching details for {len(pmids)} papers...")
    papers_data = []
    # Fetch in batches to avoid overwhelming the API
    batch_size = 100
    for i in range(0, len(pmids), batch_size):
        batch_pmids = pmids[i:i+batch_size]
        try:
            handle = Entrez.efetch(db="pubmed", id=batch_pmids, rettype="medline", retmode="xml")
            records = Entrez.read(handle)
            handle.close()
            # Ensure records['PubmedArticle'] is always a list
            articles = records.get('PubmedArticle', [])
            if not isinstance(articles, list):
                 articles = [articles] # Wrap single article in a list

            for article in articles:
                 papers_data.append(article)
            logger.info(f"Fetched details for batch {i//batch_size + 1}")
        except Exception as e:
            logger.error(f"Error fetching details for batch {i//batch_size + 1}: {e}")
            # Optionally, add partial results or skip the batch
    logger.info(f"Successfully fetched details for {len(papers_data)} papers.")
    return papers_data


def is_non_academic(affiliation: str, email: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Determines if an affiliation/email suggests a non-academic institution.
    Returns (is_non_academic, company_name_guess).
    """
    affiliation_lower = affiliation.lower() if affiliation else ""
    email_lower = email.lower() if email else ""

    # Heuristic 1: Check for company keywords in affiliation
    for keyword in COMPANY_KEYWORDS:
        if keyword in affiliation_lower:
            # Try to extract a potential company name (simple heuristic)
            parts = affiliation.split(',')
            company_name = parts[0].strip() # Assume first part is company name
            return True, company_name

    # Heuristic 2: Check email domain against academic domains
    if email:
        is_academic_domain = any(domain in email_lower for domain in ACADEMIC_DOMAINS)
        if not is_academic_domain:
             # If not clearly academic, check if affiliation gives clues
             if any(keyword in affiliation_lower for keyword in COMPANY_KEYWORDS):
                 parts = affiliation.split(',')
                 company_name = parts[0].strip()
                 return True, company_name
             # If email domain is non-academic but affiliation is unclear,
             # consider it potentially non-academic but without a company name guess.
             # You might refine this logic based on observed patterns.
             # return True, None # Or return False if you want stricter criteria

    # Heuristic 3: More advanced checks could be added here (e.g., using external databases)

    return False, None


def process_papers(papers_data: List[Dict]) -> List[Dict]:
    """Processes fetched paper data to extract required fields and identify non-academic authors."""
    results = []
    logger.info(f"Processing {len(papers_data)} fetched papers...")
    for paper in papers_data:
        try:
            medline_citation = paper.get('MedlineCitation', {})
            article = medline_citation.get('Article', {})
            pubmed_data = paper.get('PubmedData', {})
            article_id_list = pubmed_data.get('ArticleIdList', {})

            pmid = medline_citation.get('PMID', '')
            title = article.get('ArticleTitle', '')
            pub_date_info = article.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {})
            # Handle different date formats
            pub_year = pub_date_info.get('Year', '')
            pub_month = pub_date_info.get('Month', '') # Could be abbreviation or number
            pub_day = pub_date_info.get('Day', '')
            publication_date = f"{pub_year}-{pub_month}-{pub_day}".strip('-') # Basic formatting

            authors = article.get('AuthorList', [])
            if not isinstance(authors, list): # Handle single author case
                authors = [authors]

            non_academic_authors_list = []
            company_affiliations_list = []
            corresponding_author_email = None

            has_non_academic_author = False

            for author in authors:
                 # Ensure author is a dictionary
                 if not isinstance(author, dict): continue

                 last_name = author.get('LastName', '')
                 fore_name = author.get('ForeName', '')
                 author_name = f"{fore_name} {last_name}".strip()

                 affiliation_info = author.get('AffiliationInfo', [])
                 if not isinstance(affiliation_info, list): affiliation_info = [affiliation_info] # Handle single affiliation

                 author_affiliation = ""
                 author_email = None # Check within affiliation info

                 if affiliation_info:
                     # Concatenate affiliations, look for email within
                     affiliations_text = []
                     for affil in affiliation_info:
                         if isinstance(affil, dict):
                             affil_text = affil.get('Affiliation', '')
                             affiliations_text.append(affil_text)
                             # Simple email check within affiliation text
                             if '@' in affil_text:
                                 # Basic extraction, might need refinement
                                 words = affil_text.split()
                                 for word in words:
                                     if '@' in word:
                                         author_email = word.strip('().,;')
                                         break
                     author_affiliation = "; ".join(affiliations_text)


                 # Check if this author is non-academic
                 is_na, company_name = is_non_academic(author_affiliation, author_email)

                 if is_na:
                     has_non_academic_author = True
                     non_academic_authors_list.append(author_name)
                     if company_name and company_name not in company_affiliations_list:
                         company_affiliations_list.append(company_name)

                 # Check for corresponding author email (often in affiliation)
                 # This is a basic check; PubMed XML structure can be complex.
                 # A more robust approach might involve specific XML tags if available.
                 if author_email and not corresponding_author_email: # Take the first found email as corresponding
                      corresponding_author_email = author_email


            # Only include papers with at least one non-academic author
            if has_non_academic_author:
                results.append({
                    "PubMedID": pmid,
                    "Title": title,
                    "Publication Date": publication_date,
                    "Non-academic Author(s)": "; ".join(non_academic_authors_list),
                    "Company Affiliation(s)": "; ".join(company_affiliations_list),
                    "Corresponding Author Email": corresponding_author_email or "N/A",
                })

        except Exception as e:
            pmid_for_error = paper.get('MedlineCitation', {}).get('PMID', 'UNKNOWN')
            logger.warning(f"Could not process paper PMID {pmid_for_error}: {e}")
            if logger.level == logging.DEBUG:
                 logger.exception("Detailed processing error:") # Log stack trace in debug mode


    logger.info(f"Finished processing. Found {len(results)} papers meeting the criteria.")
    return results

def output_results(results: List[Dict], output_file: Optional[str]):
    """Outputs the results to a CSV file or the console."""
    if not results:
        logger.info("No results to output.")
        return

    df = pd.DataFrame(results)

    if output_file:
        try:
            df.to_csv(output_file, index=False, encoding='utf-8')
            logger.info(f"Results successfully saved to {output_file}")
        except Exception as e:
            logger.error(f"Error writing results to CSV file {output_file}: {e}")
    else:
        # Print to console (might be long)
        logger.info("Outputting results to console:")
        print(df.to_string(index=False))


def main():
    """Main execution function."""
    parser = setup_arg_parser()
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled.")

    if not Entrez.email or Entrez.email == "your.email@example.com":
         logger.error("Please set your email address for Entrez API calls in the script.")
         sys.exit(1)


    pmids = search_pubmed(args.query)
    if not pmids:
        logger.info("No papers found matching the query.")
        sys.exit(0)

    papers_data = fetch_paper_details(pmids)
    if not papers_data:
        logger.info("Could not fetch details for the found papers.")
        sys.exit(0)

    processed_results = process_papers(papers_data)

    output_results(processed_results, args.file)

if __name__ == "__main__":
    main()
