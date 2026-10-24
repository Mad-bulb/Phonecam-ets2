# PhoneCam for ETS2

Use your Android phone as a head-tracking camera in Euro Truck Simulator 2. Free and open source.

Phone (ARCore tracking) -> Wi-Fi -> **PhoneCam Hub** (Windows) -> opentrack -> ETS2

## Install

1. Download `PhoneCamHub.exe` and `PhoneCam.apk` from the **Releases** page.
2. Install [opentrack](https://github.com/opentrack/opentrack/releases). Set Input to **UDP over network** (port 4242) and Output to **freetrack 2.0 Enhanced**, then press Start.
3. Run `PhoneCamHub.exe` and allow it through the Windows firewall (private network).
4. Install `PhoneCam.apk` on your phone (allow installs from unknown sources). It needs an ARCore-compatible phone.
5. Phone and PC on the same Wi-Fi. Open PhoneCam, tap **Find PC** (or type the address shown in the hub), tap **Start sending**.
6. Start ETS2, hold the phone upright in portrait, and press **Recenter**.

If a direction is backwards, tick the matching **Invert** box in the hub. Use the sliders to tune sensitivity and smoothing.

## Limits

Head-look and small in-cab movement only. No walking out of the truck, and no drone or chase cameras.
Not compatible with TruckersMP, and untested with other games.
