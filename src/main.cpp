#include "ui/capra_ui.h"

#include <QApplication>
#include <QLocale>
#include <QTranslator>

int main(int argc, char *argv[])
{
    // Initialize ROS 2 first (before QApplication)
    // This is needed for proper ROS 2 initialization
    
    QApplication a(argc, argv);
    
    // Needed for VTK rendering in Qt (only when PCL/VTK visualization enabled)
#if defined(WITH_PCL_VIS)
    QSurfaceFormat::setDefaultFormat(QVTKOpenGLNativeWidget::defaultFormat());
#endif


    QTranslator translator;
    const QStringList uiLanguages = QLocale::system().uiLanguages();
    for (const QString &locale : uiLanguages) {
        const QString baseName = "CAPRA_UI_" + QLocale(locale).name();
        if (translator.load(":/i18n/" + baseName)) {
            a.installTranslator(&translator);
            break;
        }
    }
    
    CAPRA_UI w;
    w.show();
    return a.exec();
}
