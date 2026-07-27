from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from .jobargs import JobArgs


@dataclass
class Job:
    """Store all the information required to run a job.
    Jobs are executed by the scheduler that shouldn't need more than the data stored here to run.
    The preprocessor examines the list of 
    Common metadata about the input file (duration_sec ...) is also buffered here.
    """

    class Action(Enum):
        Create = 0      # The output file does not exist and will be created
        Overwrite = 1   # The output file exists and will be overwritten
        Skip = 2        # The output file exists and will not be overwritten

    input_path: Path                # Path to the input file for this job
    output_path: Path               # Path to the output file for this job
    args : JobArgs                  # Arguments for the ffmpeg command
    error_msg : str = ""            # An error occurred while parsing this job, string error message
    action : Action = Action.Skip   # Action to perform
    duration_sec : float = 0        # Duration of the input file in seconds