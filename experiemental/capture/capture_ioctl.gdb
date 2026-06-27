# GDB script: read-only trace of kbase ioctls on /dev/mali0.
#
# Usage (on RK3588 with debug symbols optional):
#   gdb -x capture/capture_ioctl.gdb --args ./your_gles_app
#
# Text log is written to $MALI_CAPTURE_LOG (default: mali_ioctl.log).
# Convert to .mcap with: python3 tools/log2mcap.py mali_ioctl.log -o test.mcap

set pagination off
set $mali_fd = -1
set $log = getenv("MALI_CAPTURE_LOG")
if $log == 0
  set $log = "mali_ioctl.log"
end
shell rm -f "$log" 2>/dev/null; true

define log_ioctl
  set $req = (unsigned int)$arg1
  set $nr = $req & 0xff
  printf "IOCTL nr=%u req=0x%x ret=%d\n", $nr, $req, $retval >> $log
  append $log
end

# Track mali fd from open
break open
commands
  silent
  finish
  if $retval > 0
    set $path = (char*)$arg0
    if $path != 0
      if strstr($path, "/dev/mali") != 0
        set $mali_fd = $retval
        printf "mali fd=%d path=%s\n", $mali_fd, $path >> $log
        append $log
      end
    end
  end
  continue
end

break ioctl
commands
  silent
  if $arg0 == $mali_fd
    set $req = (unsigned int)$arg1
    set $nr = $req & 0xff
    printf "IOCTL nr=%u req=0x%x\n", $nr, $req >> $log
    append $log
    finish
    printf "  ret=%d\n", $retval >> $log
    append $log
  else
    continue
  end
  continue
end

run
