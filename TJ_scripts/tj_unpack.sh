cat *.tar.gz|tar -xzvf - -i # распаковать все архивные файлы
find . -type f -size -10c -delete # удалить файлы меньше 10 байт - пустые
find . -type d -empty -delete # удалить пустые директории
find . -type f -name "*.tar.gz" -delete