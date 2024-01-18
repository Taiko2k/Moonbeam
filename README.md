
<div align="center">
<img src="com.github.taiko2k.moonbeam.svg" alt="Alt text" width="80" height="80"//>
 
## Moonbeam VRC
A VRChat companion app for Linux. 
</div>

Intended to be an alternative to [VRCX](https://github.com/vrcx-team/VRCX), but maybe narrower in scope.

### Screenshots

<table>
  <tr>
    <td align="center"><img src="https://github.com/Taiko2k/Moonbeam/assets/17271572/69cd6e1f-bf20-4cfc-a2c9-4490656438d0" alt="login"></td>
    <td align="center"><img src="https://github.com/Taiko2k/Moonbeam/assets/17271572/351321c2-868c-49cb-a08a-0054c1510643" alt="user info"></td>
  </tr>
</table>

### Building a Flatpak

You will need the package `flatpak-builder`.

 1. Clone or download this repo, and enter that directory.
     > git clone https://github.com/Taiko2k/Moonbeam.git
     > cd Moonbeam
 2. Install needed runtime and SDK (~1.3GB):
    > flatpak install --user flathub org.gnome.Platform//45 org.gnome.Sdk//45
 3. Build and install:
    > flatpak-builder --user --install --force-clean build-dir com.github.taiko2k.moonbeam.json

You can then launch the app from your desktop launcher.

You can uninstall Moonbeam and/or the SDK using:

> flatpak uninstall --user com.github.taiko2k.moonbeam org.gnome.Sdk//45

 

### Implemented features

 - See which of your friends are online
 - View friend bio information
 - Location tracker
 - Youtube URL extraction

⚠️ Warnings:

 1. This app is early in development, it may be buggy or even not work at all.
 2. This app tries to be nice to the VRChat API, but there's no guarantee.
 3. Account switching is not currently supported. Behavior when logging in with various different accounts is undefined.


