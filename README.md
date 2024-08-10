# FFMPEG-BATCH
![Screenshot 2024-08-03 104345](https://github.com/user-attachments/assets/386996db-d94f-41ab-83ff-bbe4bd0f861d)

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#usage">Usage</a></li>
        <li><a href="#presets">Presets</a></li>
      </ul>
    </li>
    <li><a href="#installing">Installing</a></li>
    <li><a href="#development">Development</a></li>
  </ol>
</details>


<!-- ABOUT THE PROJECT -->
## About The Project
This is a python script to batch process videos using ffmpeg. The script evaluates the list of input files and directories provided and converts all files to the specified output directory. The conversion is done with ffmpeg using the command line argument from one of the available presets.

### Usage
    usage: ffbatch [-h] [-r] [-f] [-v] [-p PRESET] -i INPUT [INPUT ...] -o OUTPUT

    Batch precess media files with ffmpeg.

    options:
      -h, --help            show this help message and exit
      -r                    recursive evaluation (include sub directories) (default: False)
      -f                    do not skip already existing output files (default: False)
      -v                    show debug output on console (default: False)
      -p PRESET             preset to use for file conversion (default: None)
      -i INPUT [INPUT ...]  input file paths or directories to be evaluated (default: None)
      -o OUTPUT             output directory where to store converted files (default: None)

### Presets
Presets are stored in the `"presets.json"` file as a dictionary,
every entry must have the folllowing keys:
+ "output_file_ext"   : the file extension of the output file
+ "ffmpeg_args"       : the arguments to pass to ffmpeg

#### Example
    {
      "Preset 1":{
        "output_file_ext": ".m2ts",
        "ffmpeg_args":{
          "c:v": "libx264",
          "c:a": "ac3",
          ...
      }
      },
      "Preset 2":{
        "output_file_ext": ".mp4",
        "ffmpeg_args":{
        ...
        }
      }
    }


<!-- INSTALLING -->
## Installing
After cloning the repository from the root directory run the command

    pip install .


<!-- INSTALLING PREREQUISITES -->
## Development
After cloning the repository create a python virtual enviroment.<br>
From the repository root directory run the follwing command:

    python -m venv .venv

After the enviroment has been created it must be activated

    .venv/Scripts/activate (windows)

    source .venv/bin/activate (linux)

And then required packages installed

    pip install -r requirements.txt

For testing the package can be installed in editable mode, changes to the code are instantly applied to the package. In editable mode there is no need to install the pakage after every change to the code.

    pip install -e .


**NOTE:** The requirements.txt file is genrated with

    pip freeze > requirements.txt
