# Third-party notices: Craft Lab

Craft Lab is made by Club Coders. It is built on the free software and fonts below,
and we are grateful to the people who made them. Each is used under its own licence;
the licence texts are at the end of this file (and the fonts' in engine/fonts/OFL.txt).

## Libraries

- Panda3D 1.10.16 (the 3D engine: the window, its drawing, sound and text)
  https://www.panda3d.org
  Copyright (c) 2008, Carnegie Mellon University. All rights reserved.
  Licence: BSD-3-Clause (Modified BSD)
- panda3d-simplepbr 0.13.1 (the lighting of the engine's graphics tiers)
  https://github.com/Moguri/panda3d-simplepbr
  Copyright (c) 2019, Mitchell Stokes
  Licence: BSD-3-Clause
- NumPy 2.5.3 (fast sums for the world and its meshes)
  https://numpy.org
  Copyright (c) 2005-2025, NumPy Developers. All rights reserved.
  Licence: BSD-3-Clause
- websockets 17.1 (talking to the class server)
  https://github.com/python-websockets/websockets
  Copyright (c) Aymeric Augustin and contributors
  Licence: BSD-3-Clause
- Pillow 12.3.0 (saving pictures: the block textures and the engine's textures)
  https://python-pillow.github.io
  Copyright (c) 1997-2011 by Secret Labs AB
  Copyright (c) 1995-2011 by Fredrik Lundh and contributors
  Copyright (c) 2010 by Jeffrey 'Alex' Clark and contributors
  Licence: MIT-CMU
- Babylon.js 9.28.0 and babylonjs-loaders 9.28.0 (Craft Lab in the browser:
  the page's 3D engine and its glTF loader)
  https://www.babylonjs.com
  Copyright Babylon.js contributors
  Licence: Apache-2.0 (the full text: web/vendor/LICENSE-babylonjs.txt)

## Fonts (engine/fonts)

- Inter (Inter-Regular.ttf, Inter-SemiBold.ttf: the windows' text)
  Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)
  Licence: SIL Open Font License 1.1
- Space Grotesk (SpaceGrotesk-Bold.ttf: titles)
  Copyright 2020 The Space Grotesk Project Authors
  (https://github.com/floriankarsten/space-grotesk)
  Licence: SIL Open Font License 1.1
- JetBrains Mono (JetBrainsMono.ttf: code)
  Copyright 2020 The JetBrains Mono Project Authors
  (https://github.com/JetBrains/JetBrainsMono)
  Licence: SIL Open Font License 1.1
- Press Start 2P (PressStart2P-Regular.ttf: pixel numbers)
  Copyright 2012 The Press Start 2P Project Authors (cody@zone38.net),
  with Reserved Font Name "Press Start 2P"
  Licence: SIL Open Font License 1.1

The fonts' licence and each font's copyright line: engine/fonts/OFL.txt.
Inter, Space Grotesk and JetBrains Mono are the Latin subsets the Club Coders website
uses, turned into .ttf files (Inter and Space Grotesk as single weights).
Press Start 2P is the upstream file, unchanged.

## Also in the downloaded Club Coders app

- Python 3.12 (https://www.python.org), Copyright (c) 2001 Python Software Foundation;
  Licence: PSF-2.0
- panda3d-gltf 1.3.0, Copyright (c) 2018, Mitchell Stokes; Licence: BSD-3-Clause
- ReportLab 4.4.4, Copyright (c) 2000-2025, ReportLab Inc.; Licence: BSD-3-Clause
- cryptography 46.0.2, Copyright (c) Individual contributors;
  Licence: Apache-2.0 or BSD-3-Clause

Panda3D, NumPy and Pillow carry further libraries inside their own builds (for example
FreeType, zlib, libpng, libjpeg and OpenBLAS), each under its own licence: see each
package's licence file (https://pypi.org/project/<name>/).

## Licence texts

### Panda3D

```
Copyright (c) 2008, Carnegie Mellon University.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.
3. Neither the name of Carnegie Mellon University nor the names of
   other contributors may be used to endorse or promote products
   derived from this software without specific prior written
   permission.

THIS SOFTWARE IS PROVIDED BY THE AUTHORS "AS IS" AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

(This is the Modified BSD License.  See also
http://www.opensource.org/licenses/bsd-license.php )
```

### panda3d-simplepbr

```
BSD 3-Clause License

Copyright (c) 2019, Mitchell Stokes
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### NumPy

```
Copyright (c) 2005-2025, NumPy Developers.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

    * Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.

    * Redistributions in binary form must reproduce the above
       copyright notice, this list of conditions and the following
       disclaimer in the documentation and/or other materials provided
       with the distribution.

    * Neither the name of the NumPy Developers nor the names of any
       contributors may be used to endorse or promote products derived
       from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### websockets

```
Copyright (c) Aymeric Augustin and contributors

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### Pillow (MIT-CMU)

```
The Python Imaging Library (PIL) is

    Copyright © 1997-2011 by Secret Labs AB
    Copyright © 1995-2011 by Fredrik Lundh and contributors

Pillow is the friendly PIL fork. It is

    Copyright © 2010 by Jeffrey 'Alex' Clark and contributors

Like PIL, Pillow is licensed under the open source MIT-CMU License:

By obtaining, using, and/or copying this software and/or its associated
documentation, you agree that you have read, understood, and will comply
with the following terms and conditions:

Permission to use, copy, modify and distribute this software and its
documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appears in all copies, and that
both that copyright notice and this permission notice appear in supporting
documentation, and that the name of Secret Labs AB or the author not be
used in advertising or publicity pertaining to distribution of the software
without specific, written prior permission.

SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.
IN NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR ANY SPECIAL,
INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```

### Babylon.js and babylonjs-loaders

Apache License 2.0: the full text is in web/vendor/LICENSE-babylonjs.txt.

### The fonts

SIL Open Font License 1.1: the full text is in engine/fonts/OFL.txt.
