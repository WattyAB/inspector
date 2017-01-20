# Inspector
Desktop application for easy plotting of series data, built on Qt and matplotlib

Requires pyqt4, which is easiest installed by e.g. `apt-get install python-qt4`

# Example use
```python
# Interactively
>>> from inspector import Inspector
>>> Inspector(range(9))
>>> Inspector(np.random.randn(100))
```
```sh
# On command line (using the generator plugin)
$ inspector --RandomGenerator generate '{"days": 2}'
```
![GUI sample image](/gui_sample.png)

Copyright Watty AB 
