const path = require("path");
const { watchFiles } = require("./watcher.js");
const { VideoProcessor } = require("./videoProcessor.js");


watchFiles((filePath, detectionType) => {
    console.log(
        "Nowy plik kalibracji",
        filePath
    );
    // const outputDir = path.join(
    //     path.dirname(filePath),
    //     "../../",
    //     "frames"
    // );
    // VideoProcessor.ExtractFrames(filePath, outputDir, 2);

    if (
        filePath.includes(
            "\\calibration\\video\\processing\\"
        )
        &&
        filePath.endsWith(".mp4")
        && detectionType === "calibration"
    ) {
        console.log(
            "Uruchamianie kalibracji dla pliku:",
            filePath);
        VideoProcessor.StartCalibration(filePath);
        return;
    }
    if(detectionType === "new_video"){
        console.log(
            "Nowy plik wideo do przetworzenia:",
            filePath
        );
        VideoProcessor.ProcessNewVideo(filePath);
    }
});

