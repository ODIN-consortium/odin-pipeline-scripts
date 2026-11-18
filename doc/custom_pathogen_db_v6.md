# ODIN Mobile Lab Database (v6)

**Build date:** 2026-06-15  
**Kraken2 image:** `community.wave.seqera.io/library/kraken2_coreutils_pigz:45764814c4bb5bf3`  
**Bracken image:** `staphb/bracken:latest`  
**NCBI datasets CLI:** v14+

---

## Overview

A targeted nucleotide reference database for taxonomic classification of Oxford Nanopore
reads with Kraken2. Designed for environmental surveillance in sub-Saharan Africa, the
database covers a defined set of bacterial, eukaryotic, and viral pathogens plus the human
genome for competitive host-read exclusion.

The targeted design (rather than a subsampled universe database) ensures full k-mer
coverage for all included taxa, including eukaryotes such as *Cryptosporidium* and *Giardia*
which are lost to subsampling in size-capped databases.

---

## System requirements

| Resource | Minimum |
|---|---|
| Free disk (build) | 80 GB on the native Linux filesystem |
| RAM (hash step) | 24 GB |
| Threads | 16 (recommended) |
| OS | Linux or WSL2 (Ubuntu 22.04/24.04). Build on native ext4, **not** on NTFS-backed mounts — Kraken2-build performs millions of small file I/O operations and NTFS via WSL 9P is 5–10× slower. |

---

## Target pathogen list

### Bacteria

| TaxID | Name | Genome source | Notes |
|---|---|---|---|
| 470 | *Acinetobacter baumannii* | NCBI reference | |
| 287 | *Pseudomonas aeruginosa* | NCBI reference | |
| 562 | *Escherichia coli* | NCBI reference | |
| 547 | *Enterobacter* (genus) | NCBI reference | |
| 573 | *Klebsiella pneumoniae* | NCBI reference | |
| 1352 | *Enterococcus faecium* | NCBI reference | |
| 1773 | *Mycobacterium tuberculosis* | NCBI reference | |
| 28901 | *Salmonella enterica* (NTS anchor) | GCF_000009505.1 | Pinned: Enteritidis P125109 — see Salmonella note |
| 54736 | *Salmonella bongori* | GCF_000252995.1 | Pinned: NCTC 12419 |
| 90370 | *Salmonella enterica* serovar Typhi | GCF_000195995.1 | Pinned: CT18 reference |
| 90371 | *Salmonella enterica* serovar Typhimurium | 3,660 assemblies | **Not NCBI** — see Salmonella note |
| 127906 | *Vibrio cholerae* O1 | NCBI reference | |
| 45888 | *Vibrio cholerae* O139 | NCBI contig-level RefSeq | No complete assemblies exist; 15 contig assemblies used |

### Eukaryotic pathogens

| TaxID | Name | Genome source |
|---|---|---|
| 498019 | *Candida auris* | NCBI reference |
| 5741 | *Giardia intestinalis* | NCBI reference |
| 5742 | *Giardia muris* | NCBI reference |
| 5807 | *Cryptosporidium parvum* | NCBI reference |
| 237895 | *Cryptosporidium hominis* | NCBI reference |
| 93969 | *Cryptosporidium meleagridis* | NCBI reference |
| 195482 | *Cryptosporidium canis* | NCBI reference |
| 83540 | *Cryptosporidium felis* | NCBI reference |

### Viruses

| TaxID | Name | Genome source |
|---|---|---|
| 2697049 | SARS-CoV-2 | NCBI virus RefSeq |
| 11320 | Influenza A virus | NCBI virus RefSeq |
| 2955291 | Influenza B (*Alphainfluenzavirus*) | NCBI virus RefSeq |
| 3052345 | Measles (*Morbillivirus*) | NCBI virus RefSeq |
| 2560602 | Mumps orthorubulavirus | NCBI virus RefSeq |
| 2846071 | Rubella virus | NCBI virus RefSeq |
| 12637 | Dengue virus | NCBI virus RefSeq |
| 186538 | Zaire ebolavirus | NCBI virus RefSeq |
| 565995 | Bundibugyo virus | NCBI virus RefSeq |
| 186540 | Sudan ebolavirus | NCBI virus RefSeq |
| 3049954 | RSV (*Orthopneumovirus*) | NCBI virus RefSeq |
| 10244 | Mpox virus | NCBI virus RefSeq |
| 3052505 | Marburg virus | NCBI virus RefSeq |
| 3052310 | Lassa virus | NCBI virus RefSeq |
| 28875 | Rotavirus A | NCBI virus RefSeq |
| 12092 | Hepatitis A virus | NCBI virus RefSeq |
| 1987126 | Hepatitis E virus | NCBI virus RefSeq |
| 12059 | Enterovirus (genus) | NCBI virus RefSeq |
| 142786 | Norovirus (genus) | NCBI virus RefSeq |
| 12080 | Poliovirus 1 | NCBI virus RefSeq |
| 12083 | Poliovirus 2 | NCBI virus RefSeq |
| 12086 | Poliovirus 3 | NCBI virus RefSeq |

### Host (competitive decontamination)

| TaxID | Name | Genome source |
|---|---|---|
| 9606 | *Homo sapiens* | NCBI reference |

**Total: 44 taxa** (13 bacteria + 8 eukaryotes + 22 viruses + 1 host)

---

## Salmonella — three mutually exclusive groups

TaxID 590 (genus *Salmonella*) is **deliberately excluded**. Including a genus-level genome
alongside child serovar genomes causes Kraken2 lowest-common-ancestor (LCA) collapse: every
k-mer shared between the genus and any serovar resolves to the genus node, eliminating
serovar-level classification.

Three non-overlapping groups replace it:

| Group | Label | TaxIDs included | Genome source |
|---|---|---|---|
| 1 | S. Typhi | 90370 + descendants | GCF_000195995.1 (CT18) |
| 2 | S. Typhimurium | 90371 + descendants | 3,660 assemblies from partner collection |
| 3 | NTS (Non-Typhi Salmonella) | 28901, 54736, 59202, 59204 (excluding 90370/90371) | GCF_000009505.1 for 28901 (Enteritidis P125109, not Typhimurium LT2) |

The S. enterica NTS anchor (TaxID 28901) is pinned to the Enteritidis P125109 genome
rather than the default LT2 (a Typhimurium strain). Using LT2 would create k-mer overlap
between the 28901-tagged and 90371-tagged sequences, reintroducing LCA collapse.

The Typhimurium collection (TaxID 90371) consists of 3,660 genome assemblies provided by a
project partner, covering TaxIDs 90371 (*S.* Typhimurium), 85569 (DT104 phage type),
1620419 (monophasic var. 5-), and related Typhimurium strains. These assemblies are not
individually listed here; they should be obtained from the same source to reproduce v6.
Each assembly FASTA was tagged with the serovar-level taxid from the partner's
`seqid2taxid.map` before library ingestion.

---

## Build procedure

### Step 1 — Download NCBI taxonomy

```bash
curl -fSL https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz -o taxdump.tar.gz
tar -xzf taxdump.tar.gz names.dmp nodes.dmp merged.dmp delnodes.dmp
# Place these files in <DB_DIR>/taxonomy/
```

### Step 2 — Download reference genomes (non-viral taxa)

For each non-viral taxid, attempt in cascade order until at least one FASTA is retrieved:

```bash
# 1. Preferred: reference genome
datasets download genome taxon <TAXID> --include genome --reference \
    --filename download.zip

# 2. Fallback: complete RefSeq
datasets download genome taxon <TAXID> --include genome \
    --assembly-level complete --assembly-source refseq \
    --filename download.zip

# 3. Fallback: complete assembly (any source)
datasets download genome taxon <TAXID> --include genome \
    --assembly-level complete --filename download.zip

# 4. Fallback: contig-level RefSeq (used for V. cholerae O139)
datasets download genome taxon <TAXID> --include genome \
    --assembly-level contig --assembly-source refseq \
    --filename download.zip

# 5. Last resort: pinned accession (used for 28901, 54736, 90370)
datasets download genome accession <ACCESSION> --include genome \
    --filename download.zip
```

For taxids with pinned accessions (28901, 54736, 90370), skip directly to step 5.

### Step 3 — Download viral genomes

```bash
# Preferred: RefSeq complete
datasets download virus genome taxon <TAXID> --refseq --complete-only \
    --filename download.zip

# Fallback: RefSeq without complete filter
datasets download virus genome taxon <TAXID> --refseq \
    --filename download.zip
```

### Step 4 — Tag FASTA headers

Every sequence header must be rewritten to the Kraken2 custom-database format before
adding to the library. This embeds the taxonomy assignment directly and eliminates the
need for an `accession2taxid` lookup file.

```bash
awk -v taxid="<TAXID>" \
    '/^>/ { print ">kraken:taxid|" taxid "|" substr($0,2); next } { print }' \
    input.fna > tagged.fna
```

For the Typhimurium partner collection, the taxid per sequence is read from the partner's
`seqid2taxid.map` rather than applying a single taxid to the whole file:

```bash
# Pseudocode — for each sequence in partner FASTA:
#   look up seqid in seqid2taxid.map → taxid
#   write header as >kraken:taxid|<taxid>|<original_header>
```

### Step 5 — Add sequences to Kraken2 library

**Important:** clear `<DB_DIR>/library/added/` before starting if any partial build exists,
to prevent stale sequences from contributing unintended LCA assignments.

```bash
# For each tagged FASTA file:
kraken2-build --add-to-library tagged.fna --db <DB_DIR>
```

### Step 6 — Build the Kraken2 hash

**Important:** delete `<DB_DIR>/seqid2taxid.map` if it exists before building. A stale map
causes Kraken2 to silently omit newly added sequences from the k-mer index.

```bash
rm -f <DB_DIR>/seqid2taxid.map

kraken2-build \
    --build \
    --db <DB_DIR> \
    --threads 16 \
    --max-db-size 17179869184   # 16 GB ceiling
```

Because the input set covers only ~44 target taxa, the actual index is substantially
smaller than the 16 GB ceiling and **no k-mer subsampling is applied**.

### Step 7 — Build Bracken k-mer distribution

```bash
bracken-build \
    -d <DB_DIR> \
    -l 150 \
    -t 16 \
    -k 35
```

Read length 150 bp is used, consistent with typical Nanopore output lengths.

---

## Validation

After a successful build, `<DB_DIR>` should contain:

```
hash.k2d
opts.k2d
taxo.k2d
seqid2taxid.map
database150mers.kmer_distrib
```

Run `kraken2-inspect --db <DB_DIR>` and verify that all target taxids appear with non-zero
k-mer counts. Check specifically that:

- TaxIDs 90370, 90371, 28901, and 54736 all have distinct k-mer entries (no LCA collapse)
- Eukaryotic taxa (Cryptosporidium, Giardia) have substantial k-mer counts
- TaxID 9606 (*Homo sapiens*) is present for competitive host decontamination

---

## Known limitations

- **Poliovirus serotypes** (TaxIDs 12080, 12083, 12086): no RefSeq entries exist at the
  serotype level. Sequences retrieved fall under the Enterovirus genus (TaxID 12059).
  Poliovirus classification therefore resolves to genus level.
- **V. cholerae O139** (TaxID 45888): only contig-level assemblies exist in RefSeq.
  Coverage is adequate but chromosomal completeness is lower than for O1.
- **Typhimurium partner collection**: reproducibility depends on access to the partner
  dataset. An alternative is to substitute NCBI Typhimurium genomes, but diversity will
  be substantially lower.
