# FFMPEG-BATCH

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#parameters">Parameters</a></li>
        <li><a href="#presets">Presets</a></li>
      </ul>
    </li>
    <li><a href="#installing-prerequisites">Installing Prerequisites</a>
      <ul>
        <li><a href="#python-virtual-enviroment">Python virtual enviroment</a></li>
      </ul>
    </li>
  </ol>
</details>


<!-- ABOUT THE PROJECT -->
## About The Project
This is a python script to batch process videos using ffmpeg. The script evaluates the list of input files and directories provided and converts all files to the specified output directory. The conversion is done with ffmpeg using the command line argument from one of the available presets.

### Parameters
`-i` specifies the input files or directories, if the input is a directory all the files inside are evaluated.\
`-r` optional, can be specified to make the evaluation recursive (include files in sub folders).\
`-o` specifies the output directory. All the evaluated input files are converted and stored in this directory
the file extension is thaken from the preset.\
`-p` specifies the preset to utilize.

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


<!-- INSTALLING PREREQUISITES -->
## Installing Prerequisites


<!-- INSTALLING PREREQUISITES -->
### Python virtual enviroment
After cloning the repository the python virtual enviroment has to be created.\
From the repository root directory run the follwing command:
  
    python -m venv .venv

After the enviroment has been created it must be activated

    .venv/Scripts/activate (windows)

    source .venv/bin/activate (linux)

And then required packages installed
    
    pip install -r .venv/requirements.txt
