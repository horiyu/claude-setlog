export SETLOG_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export JAVA_HOME=$SETLOG_HOME/jdk
export ANDROID_SDK_ROOT=$SETLOG_HOME/sdk
export ANDROID_HOME=$ANDROID_SDK_ROOT
export ANDROID_AVD_HOME=$SETLOG_HOME/avd
export PATH=$JAVA_HOME/bin:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$PATH

# A fresh clone starts from the sample settings; state/capture.conf is yours to edit.
[ -f "$SETLOG_HOME/state/capture.conf" ] ||
  cp "$SETLOG_HOME/state/capture.conf.example" "$SETLOG_HOME/state/capture.conf"
