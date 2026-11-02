"use strict";

const path = require("path");

function glbOutputPath(sessionDir, filename, jobType = "legacy") {
  // prepareImage() stores system frames as frame.<extension>. The Python
  // stages write frame/frame_planes.glb and the adjacent convention sidecar,
  // regardless of the frameId-based filename received from the server.
  const imageName = jobType === "system_frame" ? "frame" : path.parse(filename).name;
  return path.join(sessionDir, imageName, `${imageName}_planes.glb`);
}

module.exports = glbOutputPath;
