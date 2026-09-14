const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");
const { sysFile } = require("./sysFIle");

class VideoProcessor {

    static RunPython(script, args = [], name = "PYTHON") {
        const py = spawn("python3", ["-u", script, ...args], {
            stdio: ["ignore", "pipe", "pipe"]
        });

        py.stdout.on("data", d =>
            console.log(`[${name}]`, d.toString().trimEnd())
        );

        py.stderr.on("data", d =>
            console.error(`[${name} ERROR]`, d.toString().trimEnd())
        );

        py.on("close", code => () => {
            console.log(`[${name}] [${args.join(" ")}] done:`, code)
        }
        );

        return py;
    }

    static RunPythonAsync(script, args = [], name = "PYTHON") {
        return new Promise((resolve, reject) => {

            const py = spawn(
                "python3",
                ["-u", script, ...args]
            );

            py.stdout.on("data", d =>
                console.log(`[${name}]`, d.toString().trimEnd())
            );

            py.stderr.on("data", d =>
                console.error(`[${name} ERROR]`, d.toString().trimEnd())
            );

            py.on("close", code => {
                console.log(`[${name}] done:`, code);

                if (code === 0)
                    resolve();
                else
                    reject(new Error(`${name} failed: ${code}`));
            });

        });
    }

    static RunProcessAsync(process, args = []) {
        return new Promise((resolve, reject) => {
            console.log(`RunProcessAsync: ${process} ${args.join(" ")}`)
            const py = spawn(
                process,
                args
            );

            py.stdout.on("data", d =>
                console.log(`[${process}]`, d.toString().trimEnd())
            );

            py.stderr.on("data", d =>
                console.error(`[${process} ERROR]`, d.toString().trimEnd())
            );

            py.on("close", code => {
                console.log(`[${process}] done:`, code);

                if (code === 0)
                    resolve();
                else
                    reject(new Error(`${process} failed: ${code}`));
            });

        });
    }

    static ExtractFrames(videoPath, outdir = null, fps = null, callback = null) {
        return new Promise((resolve, reject) => {
            if (!videoPath.endsWith(".mp4")) return;

            outdir ??= sysFile.GetFramesDir(videoPath);
            console.log("Wyodrębniam klatki z:", videoPath, "do:", outdir);
            fs.mkdirSync(outdir, { recursive: true });
            let arg_fps = [];
            if(fps != null)
                arg_fps = ["-vf", `fps=${fps}`];

            const ffmpeg = spawn("ffmpeg", [
                "-hwaccel", "cuda",
                "-i", videoPath,
                ...arg_fps,
                path.join(outdir, "frame_%04d.png")
            ]);

            ffmpeg.stderr.on("data", d =>
                console.log("[FFMPEG]", d.toString().trimEnd())
            );

            ffmpeg.on("close", code => {
                console.log("FFmpeg end:", code);
                if (code === 0) {
                    callback?.(outdir);
                    resolve();
                } else {
                    reject(code)
                }
            });
        });
    }


    static StartCalibration(videoFile = null, deviceId = null, userId = null) {
        deviceId ??= sysFile.GetDeviceId(videoFile);
        userId ??= sysFile.GetUserId(videoFile);
        console.log("Start kalibracji dla:", deviceId);

        const args = [
            "--device", deviceId,
            "--user", userId
        ];

        if (videoFile)
            args.push("--videoFile", videoFile);

        return this.RunPython(
            sysFile.CalibrateScriptPath,
            args,
            "CALIBRATION"
        );
    }


    static UndistortFrames(videoPath) {
        console.log("Start undistortionu for:", videoPath);
        const inputDir = sysFile.GetFramesDir(videoPath);
        const devicePath = sysFile.GetDevicePath(videoPath);

        return this.RunPython(
            sysFile.UndistortScriptPath,
            [
                "--inputPath", inputDir,
                "--calibrationPath",
                path.join(
                    devicePath,
                    "calibration",
                    "current",
                    "camera.yaml"
                ),
                "--outputPath",
                `${inputDir}_undistorted`
            ],
            "UNDISTORT"
        );
    }


    static async GenerateEdgeContourLine(videoPath) {
        const dir = sysFile.GetFramesDir(videoPath);

        if (!fs.existsSync(dir))
            return console.error("Brak katalogu klatek:", dir);

        let frames = fs.readdirSync(dir)
            .filter(f => /\.(jpg|jpeg|png)$/i.test(f))
            .sort();

        if (!frames.length)
            return console.log("Brak klatek w katalogu:", dir);
        frames = frames.slice(0, 2);
        for (const file of frames) {
            await this.RunPythonAsync(
                sysFile.GenerateEdgeContourLinePath,
                [
                    "--imgPath",
                    path.resolve(dir, file)
                ],
                "EDGE"
            );
        }
    }

    static RunColmap(videoPath) {
        console.log("RunColmap:", videoPath);
        const inputDir = sysFile.GetProjectDir(videoPath);
        return this.RunPythonAsync(
            sysFile.ColmapScriptPath,
            [
                "-i", inputDir,
            ],
            "COLMAP"
        );
    }

    // static async RunColmapGeometr2(videoPath) {
    //     console.log("RunColmapGeometr2:", videoPath);
    //     colmap patch_match_stereo ^
    //         --workspace_path C: \...\dense ^
    //             --workspace_format COLMAP ^
    //                 --PatchMatchStereo.geom_consistency true
    //     const inputDir = sysFile.GetProjectDir(videoPath);
    //     return await this.RunPythonAsync(
    //         sysFile.ColmapScriptPath,
    //         [
    //             "--inputPath", inputDir,
    //         ],
    //         "COLMAP"
    //     );
    // }

    // static async RunColmapPhotometric2(videoPath) {
    //     console.log("RunColmapPhotometric2:", videoPath);

    //     const inputDir = sysFile.GetProjectDir(videoPath);
    //     return await this.RunPythonAsync(
    //         sysFile.ColmapScriptPath,
    //         [
    //             "--inputPath", inputDir,
    //         ],
    //         "COLMAP"
    //     );
    // }

    static RunOpenMVS(videoPath) {
        const inputDir = sysFile.GetProjectDir(videoPath);
        const outdir = inputDir.concat("/openmvc");
        fs.mkdirSync(outdir, { recursive: true });
        this.RunProcessAsync("InterfaceCOLMAP", [
            "-i", inputDir.concat("/dense"),
            "-o", outdir.concat("/scene.mvs")
        ]);
    }
    static SelectFrames(videoPath) {
        const inputDir = sysFile.GetProjectDir(videoPath) + "\\frames";
        return this.RunPythonAsync(
            sysFile.SelectFramesScriptPath,
            [
                "-i", inputDir
            ]
        );
    }

    static async ProcessNewVideo(videoPath) {
        console.log("Przetwarzam nowe video:", videoPath);

        await this.ExtractFrames(videoPath);
        await this.SelectFrames(videoPath);
        await this.RunColmap(videoPath);
        await this.RunOpenMVS(videoPath);
    }

    static async ProcessVideoByOpenMVS(videoPath) {
        console.log("Przetwarzam nowe video ByOpenMVS:", videoPath);
        const inputDir = sysFile.GetProjectDir(videoPath);
        const outdir = inputDir.concat("/openmvc");
        fs.mkdirSync(outdir, { recursive: true });
        //ExtractKeyframes -i pano.mp4 -o scene_keyframes.sfm -d frames --camera-type 1
        await this.RunProcessAsync("ExtractKeyframes", [
            "-i", videoPath,
            "-o", outdir.concat("/scene_keyframes.sfm"),
            "-d frames --camera-type 1"
        ]);
    }
}

module.exports = { VideoProcessor };