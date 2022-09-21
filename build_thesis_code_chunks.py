#! /usr/bin/env python
import os
import sys
import pipes
import argparse
import itertools

USAGE = """\
'a'\ build_thesis_code_chunks.py [-h] [-J] [thesis_code.py args]
"""
jobscript = """\
#!/bin/bash --login
###
#job name
#SBATCH --job-name='sam_praill_job_{name}'
#job stdout file
#SBATCH --output=bench.out.%J
#job stderr file
#SBATCH --error=bench.err.%J
#maximum job time in D-HH:MM
#SBATCH --time=3-00:00
#number of parallel processes (tasks) you are requesting - maps to MPI processes
#SBATCH --ntasks=1
#memory per process in MB
#tasks to run per node (change for hybrid OpenMP/MPI)
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=40
{chunks}###
#now run normal batch commands
module load python/3.7.0
{gpu}{command}"""
import thesis_code as tc


def get_unique_dir(pattern, start=1):
    path = pattern.format(start)
    while os.path.exists(path):
        start += 1
        path = pattern.format(start)
    return path


def get_commands(args, tc_args, given_args, pickles_dir):
    commands = []
    if args.create_job_script:
        chunk_range = ["$SLURM_ARRAY_TASK_ID"]
    else:
        chunk_range = range(1, tc_args.chunks + 1)
    for chunk in chunk_range:
        sanitised_args = [
            pipes.quote(s)
            for s in given_args
            + [
                "--force",
                "-u",
                "60",
                "--output",
            ]
        ]
        sanitised_args.extend(
            [
                os.path.join(pickles_dir, "out.{}.pkl".format(chunk)).replace(
                    " ", r"\ "
                ),
                "-I",
                str(chunk),
            ]
        )
        command_parts = [
            "python3",
            tc.__file__,
        ] + sanitised_args
        commands.append(" ".join(command_parts))
    return commands


def validate_args(tc_args):
    if tc_args.chunk_id is not None:
        raise ValueError(
            "Chunk ID shouldn't be provided to this script. It's determined internally for each jobscript."
        )
    if tc_args.chunks is None:
        raise ValueError("No chunks specified.")


def main():
    parser = argparse.ArgumentParser(usage=USAGE)
    parser.add_argument("-J", "--create-job-script", action="store_true")
    given_args = sys.argv[1:]
    args, given_args = parser.parse_known_args(given_args)
    tc_parser = tc.get_parser()
    tc_args = tc_parser.parse_args(list(given_args))
    validate_args(tc_args)

    var_str = "no_params"
    if tc_args.params is not None:
        ignore_vars = {"max_tile_size"}
        var_str = "_".join(
            "{}_{}".format(k, v)
            for k, v in itertools.chain.from_iterable(tc_args.params)
            if k not in ignore_vars
        )

    if tc_args.output is not None:
        dirname = os.path.dirname(tc_args.output)
        var_str += "_" + os.path.splitext(os.path.basename(tc_args.output))[0]
        results_dir = "results.{}_{{}}".format(var_str)
        if dirname:
            results_dir = os.path.join(dirname, results_dir)
    else:
        results_dir = "results.{}_{{}}".format(var_str)

    job_root = get_unique_dir(results_dir)
    pickles_dir = os.path.join(job_root, "pickles")
    commands = get_commands(args, tc_args, given_args, pickles_dir)
    print("Job root dir: {}\nCommands:\n\n{}\n".format(job_root, "\n".join(commands)))
    if args.create_job_script:
        if tc_args.gpu:
            gpu_cmds = (
                "#SBATCH -p gpu  # to request P100 GPUs\n"
                "module load cuda/11.3\n"
                "python3 -m pip install cupy-cuda113\n"
            )
        else:
            gpu_cmds = ""
        for dir_path in (job_root, pickles_dir):
            os.makedirs(dir_path)
        job_script_path = os.path.join(job_root, "job.sh")
        chunks_config = "#SBATCH --array=1{}\n".format(
            "-{}".format(tc_args.chunks) if tc_args.chunks > 1 else ""
        )
        with open(job_script_path, "w") as f:
            f.write(
                jobscript.format(
                    name=var_str,
                    command=commands[0],
                    gpu=gpu_cmds,
                    chunks=chunks_config,
                )
            )
        print(
            "To run the jobscripts, run the following command:\n\n{}".format(
                "sbatch --account=scw1772 {}".format(
                    job_script_path.replace("\\", "\\\\")
                )
            )
        )


if __name__ == "__main__":
    main()
