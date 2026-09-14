const path = require("path");
const { watchFiles } = require("./watcher.js");
const { VideoProcessor } = require("./videoProcessor.js");


watchFiles((filePath, detectionType) => {
    switch(detectionType){
        case "calibration":
            console.log(
                "Uruchamianie kalibracji dla pliku:",
                filePath);
            VideoProcessor.StartCalibration(filePath);
            return;
            case "new_video":
            console.log(
                "Nowy plik wideo do przetworzenia:",
                filePath
            );
            VideoProcessor.ProcessNewVideo(filePath);
            return;
    }
});

