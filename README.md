# Get Papers List

This project fetches research papers from the PubMed API based on a user-specified query. It identifies papers with at least one author affiliated with a pharmaceutical or biotech company and returns the results as a CSV file.

## Installation

1.  Clone the repository:

    ```bash
    git clone <repository_url>
    ```

2.  Install the dependencies using Poetry:

    ```bash
    poetry install
    ```

## Usage

```bash
poetry run python get_papers_list.py -h
```

## Run Command

```bash
poetry run get-papers-list "<search-query>" -f <output-file-path>
```

#### Example -

```bash 
poetry run get-papers-list "biotechnology AND drug" -f output_files/biotech-drugs.csv
```
