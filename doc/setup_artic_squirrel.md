# Installation Guide: artic/squirrel for Mpox Analysis

This guide walks you through installing the artic pipeline and squirrel for Mpox analysis.

---

## 1. Nextflow Configuration

Before running artic, ensure Nextflow is not in offline mode.

### Disable Nextflow Offline Mode

Edit your `.bashrc` file and **comment out** the following line (add a `#` at the start):

```bash
# export NXF_OFFLINE='true'
```

Restart your terminal after editing.

---

## 2. Install the artic Pipeline

Run:

```bash
nextflow run artic-network/artic-mpxv-nf --help
```

If you encounter errors, first pull the pipeline:

```bash
nextflow pull artic-network/artic-mpxv-nf
```

---

## 3. Download Primer Schemes

1. Go to [quick-lab/primerschemes](https://github.com/quick-lab/primerschemes).
2. Click the green **Code** button and select **Download ZIP**.
3. Unzip the downloaded file.
4. Create a folder named `primer-schemes` inside your `store_dir` (e.g. `\\wsl.localhost\Ubuntu\home\odin-ml\store_dir`).
5. Move the `artic-inrb-mpox` folder from the unzipped content into `store_dir/primer-schemes/`.

> **Tip:** You can add other primer schemes to `store_dir/primer-schemes/` in the same way.

---

## 4. Re-enable Nextflow Offline Mode (Optional)

If you need Nextflow offline, **uncomment** the line in `.bashrc`:

```bash
export NXF_OFFLINE='true'
```

Restart your terminal.

---

## 5. Install Conda

Download and install Miniforge (a minimal Conda installer):

```bash
wget "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh
```

---

## 6. Activate Conda Environment

Initialize Conda in your shell:

```bash
eval "$(/home/odin-ml/miniforge3/bin/conda shell.bash hook)"
```

---

## 7. Install squirrel

Create and activate a Conda environment for squirrel:

```bash
conda create -c bioconda -c conda-forge -n squirrel -y squirrel
conda activate squirrel
```

> **Important — IQ-TREE 3 is required, but needs a symlink:**
>
> squirrel 1.3.2 uses two snakemake scripts that call different binary names:
> - `phylo.smk` calls `iqtree3` (basic phylo tree)
> - `reconstruction.smk` calls `iqtree` (APOBEC3 reconstruction)
>
> Install IQ-TREE 3 and add an `iqtree` symlink so both scripts find the binary.
> On NORCE machines, pass the corporate CA cert to avoid SSL errors:
>
> ```bash
> conda install -n squirrel -c bioconda -c conda-forge "iqtree>=3" \
>     --ssl-verify /mnt/c/ProgramData/NORCE/cer/NORCE_CA.cer
>
> # Symlink so reconstruction.smk's `iqtree` call resolves to IQ-TREE 3:
> ln -sf ~/miniforge3/envs/squirrel/bin/iqtree3 \
>        ~/miniforge3/envs/squirrel/bin/iqtree
>
> iqtree3 --version   # should show 3.x
> iqtree  --version   # should also show 3.x via symlink
> ```
>
> **`--seqtype DNA` is required but squirrel doesn't pass it:**
>
> IQ-TREE 3 will not auto-detect DNA when most sequences consist of ambiguous bases
> (all N's), which is normal for low-coverage mpox samples. squirrel 1.3.2 does not
> pass `--seqtype DNA`, so IQ-TREE 3 fails with `ERROR: Unknown sequence type`.
>
> This is solved by wrapper scripts in `pipeline_scripts/wrappers/` (`iqtree` and
> `iqtree3`) that intercept calls from squirrel's snakemake and inject `--seqtype DNA`
> before delegating to the real IQ-TREE 3 binary. `start_mpox.sh` prepends
> `pipeline_scripts/wrappers/` to `PATH` automatically before calling squirrel, so no
> manual step is needed. The wrappers are version-controlled and survive `conda update`.
>
> **What breaks if you pin to IQ-TREE 2 instead:**
> IQ-TREE 2 provides `iqtree2` and `iqtree → iqtree2`, but no `iqtree3`. The `phylo.smk`
> step silently fails (no phylo tree), and the APOBEC3 reconstruction uses the older format.

---

## 8. Verify squirrel Installation

Check the installed version:

```bash
squirrel -v
iqtree3 --version   # confirm 3.x
iqtree  --version   # confirm 3.x (via symlink)
```

---

