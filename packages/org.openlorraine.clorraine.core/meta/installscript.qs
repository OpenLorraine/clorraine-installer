/*
 * Post-extraction check for the core component.
 *
 * The installer extracts the release binaries before component operations run.
 * Executing `clc --version` proves that the installed compiler starts on this
 * machine. A failure aborts installation instead of leaving a broken toolchain.
 */

function Component()
{
}

Component.prototype.createOperations = function()
{
    component.createOperations();

    var extension = (systemInfo.kernelType === "winnt") ? ".exe" : "";
    component.addOperation("Execute", "@TargetDir@/bin/clc" + extension, "--version");
};
