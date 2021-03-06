set transparency=10
" fonts
set guifont=Monaco:h9
set guifontwide=Monaco:h9
" maximize window
set lines=80 columns=250
set imdisable

" reset guioption
set guioptions&

" use cui
set guioptions+=c

" hide menu & toolbars
set guioptions-=T
set guioptions-=m
set background=dark

" make tabs more readable
" set guitablabel=%N\ %t%M

" new window menu
" menu File.New\ Window <Nop>
" macm File.New\ Window action=newWindow: key=<D-n>

" send print jobs to Preview.app
set printexpr=system('open\ -a\ Preview\ '.v:fname_in)\ +\ v:shell_error
