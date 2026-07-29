const chokidar = require("chokidar");
const path = require("path");
const fs = require("fs");

function watchFiles(callback) {
    const ROOT = path.resolve(__dirname,"../");
    const WATCH_PATH = path.join(ROOT,"users");

    const watcher = chokidar.watch(
        WATCH_PATH,
        {
            persistent: true,
            ignoreInitial: true
        }
    );

    console.log("Watcher path:", WATCH_PATH, watcher.getWatched());

    watcher
        .on("ready", () => {
            console.log("File watcher running");
        });

    watcher.on(
        "add",
        (filePath) => {
            const normalized = filePath.replace(/\\/g, "/");

            if (normalized.includes("/calibration/video/processing/")
                && normalized.endsWith(".mp4")) {
                if (callback) {
                    callback(filePath, "calibration");
                }
                return;
            }
            // console.log(
            //     "Nowy plik:",
            //     filePath
            // );
            if (normalized.includes("/videos/")
                && normalized.endsWith(".mp4")) {
                if (callback) {
                    callback(filePath, "new_video");
                }
                return;
            }
        }
    );
}

module.exports = {
    watchFiles
};