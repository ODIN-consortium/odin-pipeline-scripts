# Troubleshooting Guide

## Overview 
This document provides troubleshooting tips for common issues encountered when setting up and running the ODIN pipelines on a mobile lab computer.

If a script fails, check:
- That the MinKNOW directory contains the expected structure with `fastq_pass` folder and barcode directories
- That the barcode directories contain `.fastq.gz` files
- That the output directory is writable
- That Nextflow and its dependencies are properly installed
- That Docker is running and accessible without `sudo`

For detailed error messages, examine the terminal output and the Nextflow execution logs in the work directory.

## Common Issues

### Stale drvfs State in WSL

Occasionally, scripts may fail with an error from `mkdir -p` such as:

```
mkdir: cannot create directory '...': File exists
```

This is caused by a **stale drvfs state** in Windows Subsystem for Linux (WSL), where the filesystem view becomes out of sync with Windows.

**Solution:**

```bash
wsl --shutdown
```

Then restart your WSL session and rerun the script.

### Metadata Validation Failures

If `verify_nanopore_metadata.py` reports errors:

- Ensure all `run_accession` values in the metadata correspond to actual directories in the MinKNOW output.
- Check that `sampling_date` is in `YYYYMMDD` format.
- Verify there are no duplicate `(run_accession, barcode)` pairs.
- Confirm required columns exist: `sampling_date`, `barcode`, `sample_id`, `run_accession`.
- Remember that `sample_id` must follow the format `{site}_{type}_*` (e.g., `SITE01_WW_001`).

### Virtual Environment Issues

If Python scripts fail with import errors:

- Ensure the venv is activated and `PYTHON_CMD` points to the correct Python.
- Run `pip install -r requirements.txt` inside the venv.
- Run `./scripts/integrity_check.sh` to validate the environment.


### Nextflow error: API rate limit exceeded
Nextflow may give the error
```
API rate limit exceeded -- Provide your GitHub user name and password to get a higher rate limit
```
This can be solved by e.g. configuring your GitHub credentials in Nextflow.

These links provide more information on how to do this:

https://www.nextflow.io/docs/latest/git.html#git-configuration

https://seqera.io/blog/configure-git-repositories-with-nextflow/

### Docker permission issues
Ensure you have completed the post-installation steps for Docker to run without `sudo`. 

### Path problems
Use absolute paths in your configuration files to avoid issues with relative paths.

### Memory errors
If you encounter memory errors, adjust the memory settings in your Nextflow configuration. 
Change the resources allocated to the pipeline by modifying the process resourceLimits for the odin profile in `./config/odin.config` file.

It might also be necessary to adjust the memory available to the WSL2 virtual machine if you are running on Windows. 
Type WSL Settings in Windows search (Windows 11) and increase the memory size, restart wsl or machine. 
See https://learn.microsoft.com/en-us/windows/wsl/wsl-config#configuration-settings-for-wslconfig.

## Running Behind a Corporate Firewall

When running `wf-metagenomics` behind a corporate firewall that performs SSL inspection, database downloads may fail with errors such as:

```

ERROR: cannot verify genome-idx.s3.amazonaws.com's certificate, issued by 'CN=Corp CA'

````

There are two main approaches to solve this:

---

### 1. Mount the Corporate CA Certificate Into the Workflow Container

If your organization provides a corporate CA certificate, you can make it available to all workflow processes by mounting it into the Docker container and pointing standard SSL tools at it.

1. Save the certificate file as `~/certs/corpCA.pem`.
2. Add the following to your `nextflow.config` adding to the existing values if some are already present:

```groovy
   docker {
     runOptions = "-v ${System.getenv('HOME')}/certs:/certs:ro"
   }

   env {
     SSL_CERT_FILE = "/certs/corpCA.pem"
   }
````
E.g. your `nextflow.config` might look like this:

```groovy
    docker {
     enabled = true
     runOptions = "--user \$(id -u):\$(id -g) --group-add 100 -v ${System.getenv('HOME')}/certs:/certs:ro"
    }
    
    env {
        PYTHONNOUSERSITE = 1
        JAVA_TOOL_OPTIONS = "-Xlog:disable -Xlog:all=warning:stderr"
        SSL_CERT_FILE = "/certs/corpCA.cer"
    }
````

3. Rerun the workflow. All download processes (`wget`, `curl`, etc.) will now trust the corporate CA.

---

### 2. Download and Unpack Databases Manually

If direct downloads are not possible, you can preload databases yourself and point the workflow to them.

1. Download the required tarballs manually, e.g.:

   ```bash
   wget --no-check-certificate https://genome-idx.s3.amazonaws.com/kraken/k2_pluspf_08gb_20241228.tar.gz
   wget --no-check-certificate https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.tar.gz
   ```

2. Create the expected directory structure:

   ```bash
   mkdir -p /path/to/store_dir/PlusPF-8/k2_pluspf_08gb_20241228_db
   tar -xvzf k2_pluspf_08gb_20241228.tar.gz -C /path/to/store_dir/PlusPF-8/k2_pluspf_08gb_20241228_db

   mkdir -p /path/to/store_dir/PlusPF-8/new_taxdump_2025-01-01_db
   tar -xvzf new_taxdump.tar.gz -C /path/to/store_dir/PlusPF-8/new_taxdump_2025-01-01_db
   ```

   The directories must match the naming convention expected by the workflow.

3. Run the workflow, pointing to your local store:

   ```bash
   nextflow run epi2me-labs/wf-metagenomics \
     --fastq "/fastq_pass" \
     --database_set "PlusPF-8" \
     --store_dir "/path/to/store_dir" \
     --out_dir "/output" \
     --amr --amr_db "card"
   ```

The workflow will reuse the preloaded database and skip the download step.

---

### Summary

* **If you can trust the corporate CA:** mount the certificate into containers (`SSL_CERT_FILE`).
* **If downloads are impossible:** manually preload the database tarballs and unpack them into the correct subdirectories under `--store_dir`.

```

