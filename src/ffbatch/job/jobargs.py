from dataclasses import dataclass


@dataclass
class JobArgs:
    """Store the arguments required to run the ffmpeg command,
    also store the name of the preset from where the arguments come from.
    """
    name : str
    out_file_ext : str
    ffmpeg_args : dict

    def __repr__(self):
        return (f'[{self.name}]\n' +
                f'  out_file_ext : {self.out_file_ext}\n' +
                f'  ffmpeg_args .: {self.ffmpeg_args}')