const fs = require('fs'); 
const path = require("path"); 
class sysFile{
    static GetDeviceId(filePath) {
        const parts =
            filePath.split(path.sep);

        const index =
            parts.indexOf("devices");

        if (index < 0)
            throw new Error(
                "Nie znaleziono devices"
            );
        return parts[index + 1];
    }

    static GetDevicePath(filePath) {
        const parts = filePath.split(/[\\/]/);
        const index = parts.lastIndexOf("devices");
        if (index < 0)
            throw new Error("Nie znaleziono devices");
        return path.normalize(parts.slice(0, index + 2).join(path.sep)) + path.sep;
    }

    static GetFramesDir(videoPath) {
        return path.join(
            videoPath.replace(".mp4", ""),
            "frames"
        );
    }

    static GetProjectDir(videoPath) {
        return path.join(
            videoPath.replace(".mp4", "")
        );
    }

    static RootPath = path.resolve(
        __dirname,
        "../"
    );

    static CalibrateScriptPath = path.join(
        this.RootPath,
        "system",
        "py",
        "calibrate_camera.py"
    );

    static UndistortScriptPath = path.join(
        this.RootPath,
        "system",
        "py",
        "undistort_frames.py"
    );
    static GenerateFrameMasksPath = path.join(
        this.RootPath,
        "system",
        "py",
        "sam3_generate_frame_masks.py"
    );
    static GenerateEdgeContourLinePath = path.join(
        this.RootPath,
        "system",
        "py",
        "cv2_edge_contour_line.py"
    );
    static ColmapScriptPath = path.join(
        this.RootPath,
        "system",
        "py",
        "colmap.py"
    );

    static createDirIfNotExists = dir => (!fs.existsSync(dir) ? fs.mkdirSync(dir) : undefined);
}

module.exports = {
    sysFile
};