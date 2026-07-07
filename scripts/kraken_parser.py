import pandas as pd
from io import StringIO

# Hierarchy of ranks and their corresponding columns.
RANK_COLUMN_MAPPING = {
    'R': 'Root',
    'D': 'Domain',
    'K': 'Kingdom',
    'P': 'Phylum',
    'C': 'Class',
    'O': 'Order',
    'F': 'Family',
    'G': 'Genus',
    'S': 'Species'
}


def enrich_kraken2_lineage(df: pd.DataFrame, rank_map: dict[str, str]) -> pd.DataFrame:
    """
        https://bisonnet.bucknell.edu/files/2021/05/Kraken2-Help-Sheet.pdf
        Input parameter df0 is a dataframe with the following columns:

        1) Percentage of fragments covered by the clade rooted at this taxon
        2) Number of fragments covered by the clade rooted at this taxon
        3) Number of fragments assigned directly to this taxon
        4) A rank code indicating (U)nclassified, (R)oot, (D)omain, (K)ingdom, (P)hylum, (C)lass,
        (O)rder, (F)amily, (G)enus, (S)pecies. Taxa that are not any of these 10 ranks have a
        rank code that is formed by using the rank code of the closest ancestor rank with a
        number indicating the distance from that rank. Ex. Lampyrinae has a rank code of
        “F1” because it is a subfamily one step below Lampyridae (the firefly family).
        5) The Taxonomic ID number from NCBI
        6) Indented Scientific Name
    """
    ordered_ranks = list(rank_map.values())

    # Prepare columns for the lineage
    for col in ordered_ranks:
        df[col] = ""

    # Keep current lineage tracker
    current_lineage = {rank: '' for rank in ordered_ranks}

    for idx, row in df.iterrows():
        rank_code = row['Rank code']
        sci_name = row['Scientific name'].strip()

        # Only consider standard taxonomic ranks (and numbered sub-ranks like G1, S1, S2)
        base_rank = rank_code if rank_code in rank_map else rank_code[0]
        if base_rank not in rank_map:
            continue

        rank_name = rank_map[base_rank]
        # Numbered rank codes (G1, S1, S2, R1, etc.) are intermediate nodes between two
        # standard ranks. We do NOT overwrite the parent rank name in the lineage tracker
        # (e.g., G1 "unclassified Salmonella" must not overwrite Genus = "Salmonella"),
        # but we DO clear sub-levels so stale children don't bleed into sibling branches.
        is_numbered_rank = rank_code != base_rank
        if not is_numbered_rank:
            current_lineage[rank_name] = sci_name

        # Always clear levels below this rank
        rank_index = ordered_ranks.index(rank_name)
        for lower_rank in ordered_ranks[rank_index + 1:]:
            current_lineage[lower_rank] = ""

        # Fill lineage columns for this row from the (possibly just-updated) tracker
        for rank in ordered_ranks:
            df.at[idx, rank] = current_lineage[rank]

    return df


def read_kraken2_report(path: str, kraken2_column_names: list[str]) -> pd.DataFrame:
    """
        1. read in the tab separated values from kraken2 file into dataframe
        2. Strip leading and trailing spaces in values
        3. Return dataframe
    """
    df0 = pd.read_csv(path, sep='\t', names=kraken2_column_names)
    # Strip leading and trailing spaces
    df_obj = df0.select_dtypes('object')
    df0[df_obj.columns] = df_obj.apply(lambda x: x.str.strip())
    return df0


def test_enrich_kraken2_lineage():
    data = """
Pct. of Frags\tNo of Frags root\tNo of Frags\tRank code\tNCBI tax ID\tScientific name
66.67\t8\t8\tU\t0\tunclassified
33.33\t4\t0\tR\t1\troot
33.33\t4\t0\tR1\t131567\t  cellular organisms
33.33\t4\t0\tR2\t2\t    Bacteria
25.00\t3\t0\tK\t3379134\t      Pseudomonadati
16.67\t2\t1\tP\t1224\t        Pseudomonadota
8.33\t1\t0\tC\t1236\t          Gammaproteobacteria
8.33\t1\t0\tO\t135623\t            Vibrionales
8.33\t1\t0\tF\t641\t              Vibrionaceae
8.33\t1\t0\tG\t662\t                Vibrio
8.33\t1\t1\tS\t666\t                  Vibrio cholerae
8.33\t1\t0\tK1\t1783270\t        FCB group
8.33\t1\t0\tK2\t68336\t          Bacteroidota/Chlorobiota group
8.33\t1\t0\tP\t976\t            Bacteroidota
8.33\t1\t0\tC\t200643\t              Bacteroidia
8.33\t1\t0\tO\t171549\t                Bacteroidales
8.33\t1\t0\tF\t815\t                  Bacteroidaceae
8.33\t1\t0\tG\t909656\t                    Phocaeicola
8.33\t1\t1\tS\t821\t                      Phocaeicola vulgatus
8.33\t1\t0\tK\t1783272\t      Bacillati
8.33\t1\t0\tP\t1239\t        Bacillota
8.33\t1\t0\tC\t91061\t          Bacilli
8.33\t1\t0\tO\t186826\t            Lactobacillales
8.33\t1\t0\tF\t1300\t              Streptococcaceae
8.33\t1\t1\tG\t1301\t                Streptococcus
"""
    df = pd.read_csv(StringIO(data), sep="\t")
    enriched_df = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

    # Test 1: Gammaproteobacteria row
    gammaproteo = enriched_df[enriched_df['Scientific name'].str.strip() == 'Gammaproteobacteria'].iloc[0]
    assert gammaproteo['Class'] == 'Gammaproteobacteria'
    assert gammaproteo['Phylum'] == 'Pseudomonadota'
    assert gammaproteo['Kingdom'] == 'Pseudomonadati'
    assert gammaproteo['Root'] == 'root'   # R2 (Bacteria) is a numbered rank and must NOT overwrite Root
    assert gammaproteo['Order'] == ''
    assert gammaproteo['Genus'] == ''

    # Test 2: Vibrio cholerae (Species)
    cholera = enriched_df[enriched_df['Scientific name'].str.strip() == 'Vibrio cholerae'].iloc[0]
    assert cholera['Species'] == 'Vibrio cholerae'
    assert cholera['Genus'] == 'Vibrio'
    assert cholera['Family'] == 'Vibrionaceae'
    assert cholera['Class'] == 'Gammaproteobacteria'

    # Test 3: Streptococcus (Genus)
    strep = enriched_df[enriched_df['Scientific name'].str.strip() == 'Streptococcus'].iloc[0]
    assert strep['Genus'] == 'Streptococcus'
    assert strep['Family'] == 'Streptococcaceae'
    assert strep['Order'] == 'Lactobacillales'
    assert strep['Species'] == ''  # Should be empty

    # Test 4: Bacilli (Class)
    bacilli = enriched_df[enriched_df['Scientific name'].str.strip() == 'Bacilli'].iloc[0]
    assert bacilli['Class'] == 'Bacilli'
    assert bacilli['Phylum'] == 'Bacillota'
    assert bacilli['Species'] == ''  # Should be empty
    assert bacilli['Genus'] == ''  # Should be empty

    # print("All lineage assertions passed")


def test_numbered_rank_inheritance():
    """
    Test that numbered rank codes (G1, S1, S2, etc.) do NOT overwrite the parent rank
    in the lineage tracker, but DO clear sub-levels.

    Regression test for: G1 'unclassified Salmonella' was overwriting Genus='Salmonella',
    causing rows under G1 to lose their correct genus assignment.
    """
    data = """Pct. of Frags\tNo of Frags root\tNo of Frags\tRank code\tNCBI tax ID\tScientific name
0.10\t794\t6\tG\t590\t                Salmonella
0.10\t786\t143\tS\t28901\t                  Salmonella enterica
0.08\t641\t1\tS1\t59201\t                    Salmonella enterica subsp. enterica
0.08\t637\t637\tS2\t340190\t                      Salmonella enterica subsp. enterica serovar Schwarzengrund
0.00\t1\t0\tS\t54736\t                  Salmonella bongori
0.00\t1\t0\tS1\t41527\t                    Salmonella bongori serovar 48:z41:--
0.00\t1\t1\tS2\t1382510\t                      Salmonella bongori serovar 48:z41:-- str. RKS3044
0.00\t1\t0\tG1\t2614656\t                  unclassified Salmonella
0.00\t1\t1\tS\t3344879\t                    Salmonella sp. HY31"""

    df = pd.read_csv(StringIO(data), sep="\t")
    enriched_df = enrich_kraken2_lineage(df, RANK_COLUMN_MAPPING)

    # G1 row: must inherit Genus='Salmonella', not overwrite it with 'unclassified Salmonella'
    g1_row = enriched_df[enriched_df['NCBI tax ID'] == 2614656].iloc[0]
    assert g1_row['Genus'] == 'Salmonella', f"Expected Genus='Salmonella', got '{g1_row['Genus']}'"
    assert g1_row['Species'] == '', f"G1 should clear Species, got '{g1_row['Species']}'"

    # S row under G1: must also inherit Genus='Salmonella'
    sp_row = enriched_df[enriched_df['NCBI tax ID'] == 3344879].iloc[0]
    assert sp_row['Genus'] == 'Salmonella', f"Expected Genus='Salmonella', got '{sp_row['Genus']}'"
    assert sp_row['Species'] == 'Salmonella sp. HY31', f"Expected Species='Salmonella sp. HY31', got '{sp_row['Species']}'"

    # S1/S2 rows: must NOT overwrite Species of their standard parent
    s1_row = enriched_df[enriched_df['NCBI tax ID'] == 59201].iloc[0]
    assert s1_row['Genus'] == 'Salmonella'
    assert s1_row['Species'] == 'Salmonella enterica'  # inherits parent S, not overwritten

    # Salmonella bongori S1: must not bleed into G1 sibling
    bongori_s1 = enriched_df[enriched_df['NCBI tax ID'] == 41527].iloc[0]
    assert bongori_s1['Species'] == 'Salmonella bongori'  # inherits parent S

    # print("All numbered rank assertions passed")


# Run tests
test_enrich_kraken2_lineage()
test_numbered_rank_inheritance()
