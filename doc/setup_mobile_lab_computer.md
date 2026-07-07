# Mobile Laboratory Setup Guide

## Overview

This guide provides instructions for setting up a mobile laboratory environment for the ODIN project, 
including all necessary software components for nanopore sequencing analysis. The primary focus is on
installing and configuring the required tools on a Windows machine using Windows Subsystem for Linux (WSL) with Ubuntu 24.04.
The setup includes Docker, Java, Nextflow, nf-core, and the ODIN utilities for running the taxonomic profiling pipeline.
This setup is designed to facilitate the analysis of nanopore sequencing data, particularly for the ODIN project,
which involves processing and analyzing microbial communities in various environments.

This guide assumes you have a basic understanding of command-line operations and familiarity with Docker and Nextflow.


## System Setup


### Installing Ubuntu on WSL

First open a windows cmd prompt then:

```bash
# List available Linux distributions
wsl --list --online

# Install Ubuntu 24.04
wsl --install -d Ubuntu-24.04
```

**Important:** if you are using a windows machine behind a corporate firewall, using a self signed certificate, you must add the environment variable ```CURL_CA_BUNDLE```
to your unix environment. It is recommended to add a line to your `.bashrc`. Start your Ubuntu instance and in a console window edit your `.bashrc`with an entry similar to the following:

```bash
export CURL_CA_BUNDLE=/mnt/c/path/to/your/selfsigned/CERTIFICATE.cer
```

### Installing Docker

1. Follow the official Docker installation guide for Ubuntu:
   [Docker Engine Installation Guide](https://docs.docker.com/engine/install/ubuntu/)

2. **Important:** Complete the post-installation steps to use Docker without sudo:
   [Post-installation steps for Linux](https://docs.docker.com/engine/install/linux-postinstall/)

### Installing Java

```bash
# Update package lists
sudo apt update

# Check Java availability
java --version

# Install Java 21 JRE
sudo apt install openjdk-21-jre-headless
```

**Important:** if you are using a windows machine behind a corporate firewall, using a self signed certificate, import the certificate into the Java keystore. Start your Ubuntu instance and in a console window run a command like the following (be sure to replace the path with the actual path to your self-signed certificate):

```bash
sudo keytool -importcert -trustcacerts -file /mnt/c/path/to/your/selfsigned/CERTIFICATE.cer -keystore /usr/lib/jvm/java-21-openjdk-amd64/lib/security/cacerts -alias myrootcert -storepass changeit -noprompt
```
You might have to do the same for the Issuing certificate if you have a chain of certificates.

### Installing Nextflow

```bash
# Download and install Nextflow
curl -s https://get.nextflow.io | bash

# Create directories if they don't exist
mkdir -p ~/.local/bin

# Move Nextflow to the bin directory
mv nextflow ~/.local/bin

# Make Nextflow executable
chmod +x ~/.local/bin/nextflow
```

#### Restart your shell session, then confirm installation:

```bash
nextflow info
```

### Installing nf-core

```bash
# Update package lists
sudo apt update

# Install Python venv package
sudo apt install python3.12-venv

# Install pip if not already installed
sudo apt install python3-pip

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install nf-core
pip install nf-core

# Install dependencies for mobile lab scripts
pip install openpyxl
```

### Install the ODIN utilities
#### Prerequisites

**Python 3**: Ensure that Python 3 is installed on your system. You can check if Python 3 is installed by running:

    ```bash
    python3 --version
    ```
   **NOTE:**
   ODIN laptops use the 'venv' environment located in: **/home/odin-ml/venv**

   For this reason, to check whether Python 3 is installed and also for the installation of the packages
   listed in **$HOME/pipeline_scripts/requirements.txt**, the venv environment must be activated first:

   ```bash
   # activate the correct environment
   source /home/odin-ml/venv/bin/activate
   
   # check python version
   python3 --version   
   ```

#### ODIN script repository
The ODIN utilites are located on a server at NORCE and may be updated from time to time. Note that this 
link expires at the end of June 2026 and will need to be updated after that date.

```bash
# Install pipeline_scripts
cd
git clone https://oauth2:NWqFdJoPszJDzKptXJDQ@gitlab.norceresearch.no/odin/pipeline_scripts.git
```

Install the required Python packages for the ODIN utilities (make sure the correct virtual environment is activated):

```bash
# Install required Python packages
pip install -r ~/pipeline_scripts/requirements.txt
```

If you later need to update the utilities then you can do this with the following:

```bash
cd ~/pipeline_scripts
git pull
cd 
```
### Finally, make the ODIN utilities available

Ensure that the script files are executable:
 ```bash
 chmod +x pipeline_scripts/scripts/*.sh
 ```

Make the ODIN utilities available by adding them to the UNIX PATH environment variable. You can cut and paste the following 
to the ubuntu command line:

```bash
cat >> .bashrc << EOF
# Make our python virtual environment executable
export PATH="\$PATH:\$HOME/pipeline_scripts/scripts"
EOF
```

This adds the `pipeline_scripts` to your PATH, allowing you to run the scripts and Python executables directly.


## Running Bash Scripts

For detailed instructions on running the Bash scripts, see [run_scripts_guide.md](./run_scripts_guide.md).

## Analysis Prerequisites

### Required Files

1. **Sequencing Data**:
   - `fastq_pass` folder containing barcode files (output from MinKNOW)

2. **Reference Databases**:
   - Databases directory structure: `for_use_in_pipeline` (e.g., `/path/to/ODIN/databases/for_use_in_pipeline`)
   - `databases.csv` file with reference database mappings

### Database Configuration

Ensure your `databases.csv` file contains the following structure:

```csv
Name,Path,Type,Description
Kraken2,/path/to/databases/kraken2_db,Taxonomic,Kraken2 standard database
Centrifuge,/path/to/databases/centrifuge_db,Taxonomic,Centrifuge bacterial/viral database
AMR,/path/to/databases/amr_db,Functional,Antimicrobial resistance genes
```

---

### Installing artic and squirrel for Mpox analysis

For detailed instructions on installing the artic pipeline and squirrel (used for Mpox sequencing and phylogenetic analysis), see:

[Setup Guide: artic/squirrel for Mpox Analysis](./setup_artic_squirrel.md)

This guide covers Nextflow configuration, pipeline installation, primer schemes, Conda setup, and squirrel installation.

---

## Running Analysis Pipelines

### Automatically start Ubuntu terminal and docker
Open terminal settings and select Ubuntu as the Default profile. Then turn on the setting "Launch on machine startup". 
This way a terminal will automatically open when you start your computer, and the docker service will be started automatically.

If  you want to run the pipeline directly from the linux command line (without using the scripts)
then you wil also need to add the following line to your `.bashrc` file in addition to the pipeline scripts:

```bash
export PATH="\$PATH:\$HOME/venv/bin"
```



### Basic Workflow

```bash
# Navigate to your project directory
cd /path/to/project

# Run the nf-core/taxprofiler pipeline
nextflow run nf-core/taxprofiler -profile docker \
  --input samplesheet.csv \
  --outdir results \
  --databases databases.csv
```

### Sample Sheet Format

Create a `samplesheet.csv` file with the following structure:

```csv
sample,run_accession,instrument_platform,fastq_1,fastq_2
sample1,run01,OXFORD_NANOPORE,/path/to/fastq_pass/barcode01,
sample2,run01,OXFORD_NANOPORE,/path/to/fastq_pass/barcode02,
```

## Troubleshooting
For common issues and troubleshooting tips, refer to the [Troubleshooting Guide](./troubleshooting.md).
