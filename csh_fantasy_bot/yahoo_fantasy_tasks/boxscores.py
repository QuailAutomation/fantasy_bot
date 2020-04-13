"""'Load league boxscores into ES."""
import os
def export_boxscores():
    """Read linescores and dump to ES."""
    # for now just load in all files and dump.  Should look into incremental dumps
    line_score_directory = "/Users/craigh/dev/box-scores/"

    for filename in os.listdir(line_score_directory):
        if filename.endswith(".json"):
            f = open(f"{line_score_directory}{filename}")
            file = f.read()
            
            continue
        else:
            continue

        break