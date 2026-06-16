{
  lib
, buildPythonPackage
, setuptools
, unmount-image
, src
}:
buildPythonPackage rec {
  pname = "mount-image-udisks";
  version = "0.1.0";
  pyproject = true;

  inherit src;

  nativeBuildInputs = [ setuptools ];
  propagatedBuildInputs = [ unmount-image ];

  doCheck = false;
  pythonImportsCheck = [ "mount_image_udisks" ];

  meta = with lib; {
    description = "Disk image mounting via udisksctl (Linux)";
    homepage = "https://github.com/MBanucu/mount-image-udisks";
    license = licenses.gpl3Only;
    maintainers = with maintainers; [ ];
  };
}
