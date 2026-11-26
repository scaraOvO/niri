if [[ -o interactive && -t 0 && -t 1 && -n ${KITTY_WINDOW_ID:-} &&
      -z ${TMUX:-} && -z ${ZSH_EXECUTION_STRING:-} ]] && (( $+commands[tmux] )); then
  tmux new-session -c "$PWD" env DUSK_FASTFETCH=1 /usr/bin/zsh
  # Detaching returns to this shell without another startup banner.
  typeset _dusk_started_tmux=1
fi

export ZIM_HOME="${ZDOTDIR:-$HOME}/.zim"
if [[ -r "$ZIM_HOME/init.zsh" ]]; then
  source "$ZIM_HOME/init.zsh"
fi

if [[ -o interactive && -t 1 && ${TERM:-dumb} != dumb &&
      ( ${DUSK_FASTFETCH:-} == 1 || ( -z ${TMUX:-} && -z ${_dusk_started_tmux:-} ) ) ]] &&
      (( $+commands[fastfetch] )); then
  unset DUSK_FASTFETCH
  fastfetch
fi
unset _dusk_started_tmux
