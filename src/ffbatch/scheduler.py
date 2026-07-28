from ffmpeg import FFmpeg, FFmpegError, Progress
from rich.progress import Progress as RichProgress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.live import Live
from rich.console import Group
from hurry.filesize import size as HurryFileSize
from .myconsole import MyConsole
from .job import Job


class Scheduler:

    def __init__(self, console : MyConsole):
        self._console = console


    def run(self, jobs : list[Job]):
        conv_progress = RichProgress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            TextColumn("[yellow]fps: {task.fields[fps]}"),
            TextColumn("[yellow]size: {task.fields[size]}"),
            TextColumn("[yellow]speed: {task.fields[speed]}x"),
            TextColumn("[light_sky_blue1] {task.fields[file_name]}"),
            transient=True
        )

        overall_progress = RichProgress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            transient=True
        )

        group = Group(
            conv_progress,
            overall_progress
        )

        live = Live(group, transient=True)

        with live:
            accumulated_time = 0
            total_time_sec = sum([x.duration_sec for x in jobs if x.action != Job.Action.Skip])
            overall_task_id = overall_progress.add_task("[red]Progress...", total=total_time_sec)
            conv_task_id = conv_progress.add_task(f'[yellow] ... ')
            files_to_process = len([x for x in jobs if x.action == Job.Action.Create or x.action == Job.Action.Overwrite])
            job_index = 0

            for job in jobs:

                if job.action == Job.Action.Skip:
                    continue

                # Create output directory if doesn't exist
                job.output_path.parent.mkdir(parents=True, exist_ok=True)

                index_of_total_str = f'{job_index} of {files_to_process}'.rjust(11)
                conv_progress.update(conv_task_id, completed=0, description=f'[yellow]{index_of_total_str}', total=job.duration_sec, fps=0, speed=0, size=0, file_name=job.output_path.name)

                try:
                    ffmpeg = (
                        FFmpeg()
                        .option("y")
                        .input(str(job.input_path))
                        .output(
                            str(job.output_path),
                            options=job.args.ffmpeg_args
                        )
                    )

                    @ffmpeg.on("progress")
                    def on_progress(progress: Progress):
                        conv_progress.update(conv_task_id, completed=progress.time.seconds, fps=progress.fps, speed=progress.speed, size=HurryFileSize(progress.size))
                        overall_progress.update(overall_task_id, completed=accumulated_time + progress.time.seconds)

                    @ffmpeg.on("completed")
                    def on_completed():
                        conv_progress.update(conv_task_id, completed=job.duration_sec)
                        nonlocal accumulated_time
                        accumulated_time += job.duration_sec
                        nonlocal job_index
                        job_index += 1

                    self._console.verbose(f"\nRunning ffmpeg with: {ffmpeg.arguments}")

                    ffmpeg.execute()

                except FFmpegError as exception:
                    print("\nAn exception has been occurred!")
                    print("- Message from ffmpeg:", exception.message)
                    print("- Arguments to execute ffmpeg:", exception.arguments)

            overall_progress.update(overall_task_id, completed=total_time_sec)