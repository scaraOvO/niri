vim.opt.termguicolors = true
vim.opt.number = true
vim.opt.cursorline = true
vim.opt.signcolumn = "yes"
vim.opt.laststatus = 3
vim.opt.showmode = false
vim.opt.statusline = " %{mode()->toupper()}  %f %m%r%=%{&filetype}  %l:%c  %p%% "

vim.opt.expandtab = true
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.softtabstop = -1
vim.opt.smartindent = true
vim.opt.breakindent = true
vim.opt.undofile = true
vim.opt.ignorecase = true
vim.opt.smartcase = true
vim.opt.scrolloff = 5
vim.opt.splitbelow = true
vim.opt.splitright = true
vim.opt.list = true
vim.opt.listchars = { tab = ">" .. " ", trail = ".", nbsp = "+" }
vim.opt.completeopt = { "menuone", "noselect" }
vim.diagnostic.config({ virtual_text = true, severity_sort = true, float = { border = "rounded" } })

vim.cmd.colorscheme("habamax")

local bg, panel, selection = "#211e30", "#292535", "#68516b"
local fg, muted, peach = "#f1e5db", "#a397ad", "#efbc99"
local blue, lilac, teal = "#9cafd2", "#c79fcb", "#92c5c1"
local highlights = {
  Normal = { fg = fg },
  NormalFloat = { fg = fg, bg = panel },
  FloatBorder = { fg = lilac, bg = panel },
  CursorLine = { bg = panel },
  CursorLineNr = { fg = peach, bg = panel, bold = true },
  LineNr = { fg = muted },
  SignColumn = { bg = bg },
  WinSeparator = { fg = selection },
  StatusLine = { fg = peach, bg = panel, bold = true },
  StatusLineNC = { fg = muted, bg = panel },
  Visual = { fg = fg, bg = selection },
  Search = { fg = bg, bg = lilac },
  IncSearch = { fg = bg, bg = peach, bold = true },
  Pmenu = { fg = fg, bg = panel },
  PmenuSel = { fg = fg, bg = selection },
  Comment = { fg = muted, italic = true },
  Constant = { fg = peach },
  String = { fg = "#a4c8aa" },
  Function = { fg = blue },
  Statement = { fg = lilac },
  Type = { fg = teal },
  PreProc = { fg = lilac },
  Special = { fg = peach },
  DiagnosticError = { fg = "#e697a1" },
  DiagnosticWarn = { fg = peach },
  DiagnosticInfo = { fg = blue },
  DiagnosticHint = { fg = teal },
}
for group, style in pairs(highlights) do
  vim.api.nvim_set_hl(0, group, style)
end
vim.g.colors_name = "dusk"
